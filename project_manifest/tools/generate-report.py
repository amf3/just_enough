#!/usr/bin/env python3
"""
generate-report: Parse eBPF container trace output and produce a
human-readable dependency report. Classifies each file access as
either present, missing, or ignorable noise.

Modes:
    Discovery (workstation) — full report, optional manifest diff
    Dump baseline           — write current ENOENT set to a baseline file
    Check baseline (CI)     — fail only if NEW missing files appear vs baseline

Usage:
    # Full discovery report
    python3 generate-report.py --log /var/log/ebpf-container-trace.log

    # Discovery report with manifest diff
    python3 generate-report.py --log ... --manifest unbound.yaml

    # Write baseline from current trace (run once on a known-good container)
    python3 generate-report.py --log ... --baseline baseline.yml --dump-baseline

    # CI drift check — fail only on new missing files vs baseline
    python3 generate-report.py --log ... --baseline baseline.yml --check-baseline
"""

import argparse
import datetime
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False


# ---------------------------------------------------------------------------
# Classification rules
# ---------------------------------------------------------------------------

# Files that are always safe to ignore. These are opened speculatively by
# libc and the dynamic linker during process startup as kernel capability
# probes — they have nothing to do with the application itself.
IGNORE_PATTERNS = [
    (r"^/$",                           "Root directory open"),
    (r"^/dev/",                        "Device file"),
    (r"^/tmp/oci-bundle/",             "OCI bundle host path (build artifact)"),
    (r"^/proc/acpi",                   "ACPI power management probe"),
    (r"^/proc/asound",                 "ALSA audio subsystem probe"),
    (r"^/proc/interrupts",             "Hardware interrupt table"),
    (r"^/proc/kcore",                  "Kernel memory ELF core"),
    (r"^/proc/keys",                   "Kernel keyring"),
    (r"^/proc/latency_stats",          "Scheduling latency debug"),
    (r"^/proc/sched_debug",            "Scheduler internals debug"),
    (r"^/proc/scsi",                   "SCSI device list"),
    (r"^/proc/timer_list",             "Kernel timer state"),
    (r"^/proc/timer_stats",            "Removed in Linux 4.11"),
    (r"^/proc/sys/kernel/cap_last_cap","Capability number probe, has fallback"),
    (r"^/proc/sys/kernel/ngroups_max", "Max groups probe, has fallback"),
    (r"^/sys/devices/virtual/powercap","CPU power capping (Intel RAPL)"),
    (r"^/sys/firmware",                "BIOS/EFI info"),
    (r"^/var/lib/docker/",             "Docker overlay layer path (host artifact)"),
    (r"^/etc/ld\.so\.cache$",          "Linker cache — optional optimisation"),
]

# Numeric-only paths are bare file descriptors leaked into the filename
# field — not real paths. Filter them before any other processing.
FD_PATTERN = re.compile(r"^\d+$")


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class FileAccess:
    elapsed_ns: int
    retval: int
    path: str

    @property
    def present(self) -> bool:
        return self.retval > 0

    @property
    def missing(self) -> bool:
        return self.retval == -2

    @property
    def is_real_path(self) -> bool:
        return self.path.startswith("/") and not FD_PATTERN.match(self.path)


@dataclass
class TraceReport:
    container_id: str
    present: list[FileAccess]      = field(default_factory=list)
    missing: list[FileAccess]      = field(default_factory=list)
    ignored: list[FileAccess]      = field(default_factory=list)
    ignore_reasons: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_log(log_path: Path, container_id: str | None) -> dict[str, list[FileAccess]]:
    """
    Parse the shared trace log and group FileAccess entries by container ID.
    Each log entry is either a hook timestamp line or a bpftrace output line.
    bpftrace output lines have the format: elapsed retval path
    """
    container_blocks: dict[str, list[FileAccess]] = {}
    current_id: str | None = None

    for line in log_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue

        # Hook log lines contain the container ID in brackets.
        # Accepts both 64-char Docker hex IDs and runc-style IDs like
        # validate-unbound_dns-26007518616
        id_match = re.search(r'\[([a-zA-Z0-9_-]+)\]', line)
        if id_match:
            current_id = id_match.group(1)
            if current_id not in container_blocks:
                container_blocks[current_id] = []
            continue

        # bpftrace output lines: elapsed retval path
        if current_id is None:
            continue

        parts = line.split(None, 2)
        if len(parts) != 3:
            continue

        try:
            elapsed = int(parts[0])
            retval  = int(parts[1])
            path    = parts[2].strip()
        except ValueError:
            continue

        container_blocks[current_id].append(
            FileAccess(elapsed_ns=elapsed, retval=retval, path=path)
        )

    if container_id:
        # Support prefix matching for convenience
        matches = {k: v for k, v in container_blocks.items()
                   if k.startswith(container_id)}
        if not matches:
            print(f"error: container ID '{container_id}' not found in log",
                  file=sys.stderr)
            sys.exit(1)
        return matches

    return container_blocks


def classify(accesses: list[FileAccess], container_id: str) -> TraceReport:
    """
    Classify each file access into present, missing, or ignored.
    Deduplicates paths — only the first access to each path is reported.
    """
    report = TraceReport(container_id=container_id)
    seen   = set()

    for access in accesses:
        if not access.is_real_path:
            continue

        path = access.path

        # Check ignore patterns first
        ignored = False
        for pattern, reason in IGNORE_PATTERNS:
            if re.match(pattern, path):
                if path not in seen:
                    report.ignored.append(access)
                    report.ignore_reasons[path] = reason
                    seen.add(path)
                ignored = True
                break

        if ignored:
            continue

        if path not in seen:
            seen.add(path)
            if access.present:
                report.present.append(access)
            elif access.missing:
                report.missing.append(access)

    return report


# ---------------------------------------------------------------------------
# Manifest diffing
# ---------------------------------------------------------------------------

def load_manifest_paths(manifest_path: Path) -> set[str]:
    """Extract all destination paths from a just_enough manifest."""
    if not YAML_AVAILABLE:
        print("warning: pyyaml not installed, skipping manifest diff", file=sys.stderr)
        return set()

    manifest = yaml.safe_load(manifest_path.read_text())
    declared = set()

    for section in ("binaries", "data"):
        for entry in manifest.get(section, []):

            # Skip non-string entries — YAML may parse 'key: value' as a dict
            if not isinstance(entry, str):
                print(f"warning: skipping non-string entry in {section}[]: {entry!r}",
                      file=sys.stderr)
                continue

            parts = entry.split(":", 1)
            if len(parts) < 2:
                print(f"warning: skipping entry with no destination in {section}[]: {entry!r}",
                      file=sys.stderr)
                continue

            dest = parts[1]
            declared.add(dest)

    for entry in manifest.get("symlinks", []):
        if not isinstance(entry, str):
            continue
        parts = entry.split(":", 1)
        if len(parts) < 2:
            continue
        link_path = parts[0]
        declared.add(link_path)

    return declared


# ---------------------------------------------------------------------------
# Baseline management
# ---------------------------------------------------------------------------

def load_baseline(baseline_path: Path) -> set[str]:
    """
    Load the set of acceptable missing files from a baseline YAML file.
    These are ENOENT results that were reviewed and accepted as non-critical
    on a known-good container run.
    """
    if not YAML_AVAILABLE:
        print("error: pyyaml required for baseline operations", file=sys.stderr)
        sys.exit(1)

    data = yaml.safe_load(baseline_path.read_text())
    return set(data.get("acceptable_missing", []))


def dump_baseline(report: TraceReport, baseline_path: Path) -> None:
    """
    Write the current ENOENT set to a baseline YAML file.
    Run this once on a known-good container to establish the reference
    point for CI drift detection. Commit the result alongside the manifest.
    """
    if not YAML_AVAILABLE:
        print("error: pyyaml required for baseline operations", file=sys.stderr)
        sys.exit(1)

    missing_paths = sorted(a.path for a in report.missing)
    timestamp     = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    lines = [
        f"# Generated:  {timestamp}",
        f"# Container:  {report.container_id}",
        "#",
        "# Acceptable ENOENT results from a known-good container run.",
        "# CI will fail if new missing paths appear that are not in this list.",
        "# Review and commit this file alongside your manifest.",
        "#",
        "acceptable_missing:",
    ]
    for path in missing_paths:
        lines.append(f"  - {path}")
    lines.append("")

    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_path.write_text("\n".join(lines))
    print(f"Baseline written to {baseline_path} ({len(missing_paths)} entries)")


def check_baseline(
    report: TraceReport,
    baseline: set[str],
) -> tuple[set[str], set[str]]:
    """
    Compare the current ENOENT set against the stored baseline.

    Returns:
        new_missing — paths missing now that were NOT in the baseline (failures)
        resolved    — paths in the baseline that are NOW present (improvements)
    """
    current_missing = {a.path for a in report.missing}
    new_missing     = current_missing - baseline
    resolved        = baseline - current_missing
    return new_missing, resolved


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

RESET  = "\033[0m"
RED    = "\033[31m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
CYAN   = "\033[36m"
BOLD   = "\033[1m"
DIM    = "\033[2m"


def color(text: str, code: str, use_color: bool) -> str:
    return f"{code}{text}{RESET}" if use_color else text


def render_report(
    report: TraceReport,
    manifest_paths: set[str] | None,
    use_color: bool,
    show_ignored: bool,
    baseline: set[str] | None = None,
) -> str:

    lines = []
    c = lambda text, code: color(text, code, use_color)

    new_missing: set[str] = set()
    resolved: set[str]    = set()
    if baseline is not None:
        new_missing, resolved = check_baseline(report, baseline)

    short_id = report.container_id[:32] + "..."
    lines.append("")
    lines.append(c("=" * 64, BOLD))
    lines.append(c("  Container Dependency Report", BOLD))
    lines.append(c("=" * 64, BOLD))
    lines.append(f"  Container : {short_id}")
    lines.append(f"  Present   : {len(report.present)} files")
    lines.append(f"  Missing   : {len(report.missing)} files")
    lines.append(f"  Ignored   : {len(report.ignored)} files (kernel probes / noise)")
    if baseline is not None:
        lines.append(f"  New (vs baseline)      : {len(new_missing)}")
        lines.append(f"  Resolved (vs baseline) : {len(resolved)}")
    lines.append(c("=" * 64, BOLD))

    # --- Present files -------------------------------------------------------
    lines.append("")
    lines.append(c(f"  FILES PRESENT  ({len(report.present)})", BOLD))
    lines.append(c("  " + "-" * 62, DIM))

    if not report.present:
        lines.append(c("  none", DIM))
    else:
        for a in sorted(report.present, key=lambda x: x.path):
            tag  = c("  OK  ", GREEN)
            note = ""
            if manifest_paths is not None:
                if a.path in manifest_paths:
                    note = c("  [declared]", DIM)
                else:
                    note = c("  [undeclared — consider adding to manifest]", YELLOW)
            lines.append(f"{tag} {a.path}{note}")

    # --- Missing files -------------------------------------------------------
    lines.append("")
    lines.append(c(f"  FILES MISSING / ENOENT  ({len(report.missing)})", BOLD))
    lines.append(c("  " + "-" * 62, DIM))

    if not report.missing:
        lines.append(c("  none", DIM))
    else:
        for a in sorted(report.missing, key=lambda x: x.path):
            is_new = a.path in new_missing
            if is_new:
                # New failure — highlight in red
                tag  = c("  !! ", RED)
                note = c("  [NEW — not in baseline]", RED)
            elif baseline is not None:
                # Known acceptable miss — dimmed
                tag  = c("  --  ", DIM)
                note = c("  [baseline]", DIM)
            else:
                # Discovery mode — no baseline context
                tag  = c("  --  ", RED)
                note = ""
                if manifest_paths is not None and a.path not in manifest_paths:
                    note = c("  [not in manifest]", YELLOW)
            lines.append(f"{tag} {a.path}{note}")

    # --- Resolved since baseline ---------------------------------------------
    if resolved:
        lines.append("")
        lines.append(c(f"  RESOLVED SINCE BASELINE  ({len(resolved)})", BOLD))
        lines.append(c("  " + "-" * 62, DIM))
        lines.append(c("  These were missing before and are now present.", DIM))
        lines.append(c("  Consider removing them from the baseline file.", DIM))
        for path in sorted(resolved):
            lines.append(f"  {c('  OK  ', GREEN)} {path}")

    # --- Manifest gaps -------------------------------------------------------
    # Only shown in discovery mode (no baseline). In CI mode the manifest
    # "never opened" section is not meaningful — utility binaries and admin
    # tools are intentionally included but won't run during a startup test.
    if manifest_paths is not None and baseline is None:
        opened_paths = {a.path for a in report.present}
        dead_entries = manifest_paths - opened_paths - {a.path for a in report.missing}
        if dead_entries:
            lines.append("")
            lines.append(c(f"  MANIFEST ENTRIES NEVER OPENED  ({len(dead_entries)})", BOLD))
            lines.append(c("  " + "-" * 62, DIM))
            lines.append(c("  Declared but not accessed in this run.", DIM))
            lines.append(c("  Normal for utility binaries — review before removing.", DIM))
            for path in sorted(dead_entries):
                lines.append(f"  {c('  ??  ', CYAN)} {path}")

    # --- Ignored files -------------------------------------------------------
    if show_ignored:
        lines.append("")
        lines.append(c(f"  IGNORED (kernel probes / noise)  ({len(report.ignored)})", BOLD))
        lines.append(c("  " + "-" * 62, DIM))
        for a in sorted(report.ignored, key=lambda x: x.path):
            reason = report.ignore_reasons.get(a.path, "")
            status = c("  ok  ", DIM) if a.present else c("  --  ", DIM)
            lines.append(f"{status} {a.path}  {c(reason, DIM)}")

    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a human-readable report from eBPF container traces.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
modes:
  discovery (default)   full report; optionally diff against manifest
  --dump-baseline       write current ENOENT set to baseline file
  --check-baseline      CI mode — fail only if new ENOENT paths appear vs baseline

examples:
  # Workstation: full discovery report with manifest diff
  generate-report.py --manifest unbound.yaml

  # Workstation: establish baseline from a known-good run
  generate-report.py --baseline baselines/unbound.yml --dump-baseline

  # CI: drift detection — fail only on new missing files
  generate-report.py --baseline baselines/unbound.yml --check-baseline
        """,
    )
    parser.add_argument(
        "--log",
        type=Path,
        default=Path("/var/log/ebpf-container-trace.log"),
        help="Path to the trace log (default: /var/log/ebpf-container-trace.log)",
    )
    parser.add_argument(
        "--container",
        type=str,
        default=None,
        help="Container ID or prefix to report on (default: all containers in log)",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Path to a just_enough manifest YAML to diff against (discovery mode)",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=None,
        help="Path to baseline YAML file (used with --dump-baseline or --check-baseline)",
    )
    parser.add_argument(
        "--dump-baseline",
        action="store_true",
        default=False,
        help="Write current ENOENT set to --baseline file (run on a known-good container)",
    )
    parser.add_argument(
        "--check-baseline",
        action="store_true",
        default=False,
        help="CI mode: fail if new ENOENT paths appear not present in --baseline file",
    )
    parser.add_argument(
        "--show-ignored",
        action="store_true",
        default=False,
        help="Include kernel probe / noise entries in output",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        default=False,
        help="Disable ANSI color output",
    )

    args      = parser.parse_args()
    use_color = not args.no_color and sys.stdout.isatty()

    # Validate flag combinations
    if args.dump_baseline and args.check_baseline:
        print("error: --dump-baseline and --check-baseline are mutually exclusive",
              file=sys.stderr)
        return 1

    if (args.dump_baseline or args.check_baseline) and not args.baseline:
        print("error: --dump-baseline and --check-baseline require --baseline <path>",
              file=sys.stderr)
        return 1

    if args.check_baseline and not args.baseline.exists():
        print(f"error: baseline file not found: {args.baseline}", file=sys.stderr)
        print("       run with --dump-baseline first to create it", file=sys.stderr)
        return 1

    if not args.log.exists():
        print(f"error: log file not found: {args.log}", file=sys.stderr)
        return 1

    # Load optional inputs
    manifest_paths = None
    if args.manifest:
        if not args.manifest.exists():
            print(f"error: manifest not found: {args.manifest}", file=sys.stderr)
            return 1
        manifest_paths = load_manifest_paths(args.manifest)

    baseline = None
    if args.check_baseline:
        baseline = load_baseline(args.baseline)

    # Parse and classify trace
    container_blocks = parse_log(args.log, args.container)
    if not container_blocks:
        print("No container trace data found in log.", file=sys.stderr)
        return 1

    exit_code = 0

    for container_id, accesses in container_blocks.items():
        report = classify(accesses, container_id)

        # --dump-baseline: write ENOENT set and show discovery report
        if args.dump_baseline:
            dump_baseline(report, args.baseline)
            print(render_report(report, manifest_paths, use_color, args.show_ignored))
            continue

        # --check-baseline: CI drift detection
        if args.check_baseline:
            new_missing, _ = check_baseline(report, baseline)
            print(render_report(
                report, manifest_paths, use_color, args.show_ignored, baseline
            ))
            if new_missing:
                print(color(
                    f"\nFAIL: {len(new_missing)} new missing file(s) detected vs baseline.",
                    RED, use_color
                ))
                exit_code = 1
            else:
                print(color(
                    "\nPASS: No new missing files vs baseline.",
                    GREEN, use_color
                ))
            continue

        # Default: discovery mode — informational, never blocks CI
        print(render_report(report, manifest_paths, use_color, args.show_ignored))

    return exit_code


if __name__ == "__main__":
    sys.exit(main())

