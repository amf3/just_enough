#!/usr/bin/env python3
"""
generate-report: Parse eBPF container trace output and produce a
human-readable dependency report. Classifies each file access as
either present, missing, or ignorable noise, and optionally diffs
against a just_enough manifest to identify gaps.

Usage:
    python3 generate-report.py --log /var/log/ebpf-container-trace.log
    python3 generate-report.py --log /var/log/ebpf-container-trace.log --manifest unbound.yaml
    python3 generate-report.py --log /var/log/ebpf-container-trace.log --container <id>
"""

import argparse
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
    present: list[FileAccess]       = field(default_factory=list)
    missing: list[FileAccess]       = field(default_factory=list)
    ignored: list[FileAccess]       = field(default_factory=list)
    ignore_reasons: dict[str, str]  = field(default_factory=dict)


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

        # Hook log lines contain the container ID in brackets
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
    report   = TraceReport(container_id=container_id)
    seen     = set()

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


def render_report(report: TraceReport,
                  manifest_paths: set[str] | None,
                  use_color: bool,
                  show_ignored: bool) -> str:

    lines = []
    c = lambda text, code: color(text, code, use_color)

    short_id = report.container_id[:16] + "..."
    lines.append("")
    lines.append(c("=" * 64, BOLD))
    lines.append(c("  Container Dependency Report", BOLD))
    lines.append(c("=" * 64, BOLD))
    lines.append(f"  Container : {short_id}")
    lines.append(f"  Present   : {len(report.present)} files")
    lines.append(f"  Missing   : {len(report.missing)} files")
    lines.append(f"  Ignored   : {len(report.ignored)} files (kernel probes / noise)")
    lines.append(c("=" * 64, BOLD))

    # --- Present files -------------------------------------------------------
    lines.append("")
    lines.append(c(f"  FILES PRESENT  ({len(report.present)})", BOLD))
    lines.append(c("  " + "-" * 62, DIM))

    for a in sorted(report.present, key=lambda x: x.path):
        tag = c("  OK  ", GREEN)
        manifest_note = ""
        if manifest_paths is not None:
            if a.path in manifest_paths:
                manifest_note = c("  [declared]", DIM)
            else:
                manifest_note = c("  [undeclared — consider adding to manifest]", YELLOW)
        lines.append(f"{tag} {a.path}{manifest_note}")

    # --- Missing files -------------------------------------------------------
    lines.append("")
    lines.append(c(f"  FILES MISSING / ENOENT  ({len(report.missing)})", BOLD))
    lines.append(c("  " + "-" * 62, DIM))

    if not report.missing:
        lines.append(c("  none", DIM))
    else:
        for a in sorted(report.missing, key=lambda x: x.path):
            tag = c("  --  ", RED)
            manifest_note = ""
            if manifest_paths is not None and a.path not in manifest_paths:
                manifest_note = c("  [not in manifest]", YELLOW)
            lines.append(f"{tag} {a.path}{manifest_note}")

    # --- Manifest gaps -------------------------------------------------------
    if manifest_paths is not None:
        opened_paths = {a.path for a in report.present}
        dead_entries = manifest_paths - opened_paths - {a.path for a in report.missing}
        if dead_entries:
            lines.append("")
            lines.append(c(f"  MANIFEST ENTRIES NEVER OPENED  ({len(dead_entries)})", BOLD))
            lines.append(c("  " + "-" * 62, DIM))
            lines.append(c("  These are declared but never accessed at runtime.", DIM))
            lines.append(c("  Consider removing them from the manifest.", DIM))
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
        description="Generate a human-readable report from eBPF container traces."
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
        help="Path to a just_enough manifest YAML to diff against",
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

    args       = parser.parse_args()
    use_color  = not args.no_color and sys.stdout.isatty()

    if not args.log.exists():
        print(f"error: log file not found: {args.log}", file=sys.stderr)
        return 1

    manifest_paths = None
    if args.manifest:
        if not args.manifest.exists():
            print(f"error: manifest not found: {args.manifest}", file=sys.stderr)
            return 1
        manifest_paths = load_manifest_paths(args.manifest)

    container_blocks = parse_log(args.log, args.container)

    if not container_blocks:
        print("No container trace data found in log.", file=sys.stderr)
        return 1

    exit_code = 0
    for container_id, accesses in container_blocks.items():
        report = classify(accesses, container_id)
        print(render_report(report, manifest_paths, use_color, args.show_ignored))

        # Exit non-zero if there are undeclared runtime dependencies
        if manifest_paths is not None:
            opened = {a.path for a in report.present}
            if opened - manifest_paths:
                exit_code = 1

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
