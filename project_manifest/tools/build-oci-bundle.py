#!/usr/bin/env python3
"""
build-oci-bundle.py: Extract a Docker image into an OCI bundle for runc.
Creates a bundle directory containing rootfs/ and a config.json with
eBPF hooks injected, ready for direct invocation via runc run.

Usage:
    python3 build-oci-bundle.py <image:tag> <bundle-dir>

Hook paths:
    By default the eBPF hook scripts are resolved from the same directory
    as this script, so a local checkout works without any extra setup.
    Override individually via environment variables if needed:

        ATTACH_HOOK=/path/to/attach-ebpf-probe \\
        DETACH_HOOK=/path/to/detach-ebpf-probe \\
        python3 build-oci-bundle.py <image:tag> <bundle-dir>

    In CI the hooks are installed to /usr/local/bin/ so no env vars are needed.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def resolve_hook_path(env_var: str, filename: str) -> str:
    """
    Resolve the path for a hook script using the following priority:

      1. Environment variable (e.g. ATTACH_HOOK=/custom/path)
      2. Same directory as this script (local development default)
      3. /usr/local/bin/<filename> (CI / system install fallback)

    Exits with a clear error if none of the candidates exist.
    """
    # 1. Explicit override via environment variable
    if env_var in os.environ:
        path = Path(os.environ[env_var])
        if not path.exists():
            print(f"error: {env_var}={path} does not exist", file=sys.stderr)
            sys.exit(1)
        return str(path)

    # 2. Co-located with this script — works for local dev without any setup
    script_dir = Path(__file__).parent.resolve()
    local_path = script_dir / filename
    if local_path.exists():
        return str(local_path)

    # 3. System install path used in CI
    system_path = Path("/usr/local/bin") / filename
    if system_path.exists():
        return str(system_path)

    print(
        f"error: hook script '{filename}' not found.\n"
        f"  Searched:\n"
        f"    {env_var} (not set)\n"
        f"    {local_path}\n"
        f"    {system_path}\n"
        f"  Set {env_var}=/path/to/{filename} to specify its location.",
        file=sys.stderr,
    )
    sys.exit(1)


def build_oci_hooks() -> dict:
    """
    Build the OCI hooks dict with paths resolved at runtime.
    Called once during bundle generation so the resolved paths are
    baked into config.json.
    """
    attach = resolve_hook_path("ATTACH_HOOK", "attach-ebpf-probe")
    detach = resolve_hook_path("DETACH_HOOK", "detach-ebpf-probe")

    print(f"  attach hook: {attach}")
    print(f"  detach hook: {detach}")

    return {
        "createRuntime": [{
            "path": attach,
            "args": ["attach-ebpf-probe"],
            "timeout": 5,
        }],
        "poststop": [{
            "path": detach,
            "args": ["detach-ebpf-probe"],
            "timeout": 5,
        }],
    }


def extract_rootfs(image: str, bundle: Path) -> None:
    """
    Export the Docker image filesystem into bundle/rootfs.
    docker export only works on containers, not images, so we create
    a temporary container and immediately export + remove it.
    """
    rootfs = bundle / "rootfs"
    rootfs.mkdir(parents=True, exist_ok=True)

    result = subprocess.run(
        ["docker", "create", image],
        capture_output=True, text=True, check=True
    )
    container_id = result.stdout.strip()

    try:
        export = subprocess.Popen(
            ["docker", "export", container_id],
            stdout=subprocess.PIPE
        )
        subprocess.run(
            ["tar", "-C", str(rootfs), "-xf", "-"],
            stdin=export.stdout,
            check=True
        )
        export.wait()
    finally:
        subprocess.run(["docker", "rm", container_id], check=True)

    print(f"  rootfs extracted to {rootfs}")


def get_image_config(image: str) -> dict:
    """
    Read CMD, ENTRYPOINT, ENV, and WORKDIR from the Docker image config.
    These need to be reflected in the OCI spec process block.
    """
    result = subprocess.run(
        ["docker", "inspect", "--format", "{{json .Config}}", image],
        capture_output=True, text=True, check=True
    )
    return json.loads(result.stdout)


def generate_spec(bundle: Path) -> None:
    """Generate a base OCI runtime spec using runc spec."""
    subprocess.run(
        ["runc", "spec"],
        cwd=str(bundle),
        check=True
    )
    print(f"  base OCI spec generated at {bundle / 'config.json'}")


def patch_spec(bundle: Path, image_config: dict, oci_hooks: dict) -> None:
    """
    Patch the generated config.json with:
      1. process.terminal = false   (no TTY in CI)
      2. root.readonly = false      (writable rootfs for pidfiles etc.)
      3. capabilities               (what this container needs to run)
      4. process args/env/cwd       (from Docker image config)
      5. OCI lifecycle hooks        (eBPF attach/detach)
    """
    config_path = bundle / "config.json"
    config = json.loads(config_path.read_text())

    # Disable terminal allocation — CI environments have no TTY
    config["process"]["terminal"] = False

    # Allow writes to rootfs — services need to write pidfiles, sockets etc.
    config["root"]["readonly"] = False

    # Capabilities required to run a privilege-dropping service like unbound.
    # Ambient is deliberately excluded — GitHub Actions runners won't permit
    # raising it and the service handles privilege drop internally.
    required_caps = [
        "CAP_SYS_CHROOT",       # chroot to /etc/unbound for privilege separation
        "CAP_SYS_RESOURCE",     # setrlimit for increasing file descriptor limits
        "CAP_SETUID",           # drop from root to service user at runtime
        "CAP_SETGID",           # drop from root to service group at runtime
        "CAP_NET_BIND_SERVICE", # bind to privileged ports (e.g. port 53)
    ]
    for cap_set in ("bounding", "effective", "permitted"):
        existing = config["process"]["capabilities"].setdefault(cap_set, [])
        for cap in required_caps:
            if cap not in existing:
                existing.append(cap)
    print(f"  capabilities set: {required_caps}")

    # Build the args list: entrypoint + cmd
    entrypoint = image_config.get("Entrypoint") or []
    cmd        = image_config.get("Cmd") or []
    args       = entrypoint + cmd
    if args:
        config["process"]["args"] = args
        print(f"  process args: {args}")

    # Carry over environment variables
    env = image_config.get("Env") or []
    if env:
        config["process"]["env"] = env

    # Set working directory
    workdir = image_config.get("WorkingDir") or "/"
    config["process"]["cwd"] = workdir

    # Inject eBPF lifecycle hooks with runtime-resolved paths
    config.setdefault("hooks", {})
    for hook_type, hook_list in oci_hooks.items():
        existing = config["hooks"].setdefault(hook_type, [])
        existing.extend(hook_list)
    print(f"  hooks injected: {list(oci_hooks.keys())}")

    # Atomic write — never leave a partially written config.json
    tmp = Path(tempfile.mktemp(dir=bundle))
    try:
        tmp.write_text(json.dumps(config, indent=2))
        tmp.rename(config_path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def main() -> int:
    if len(sys.argv) != 3:
        print(f"usage: {sys.argv[0]} <image:tag> <bundle-dir>", file=sys.stderr)
        return 1

    image  = sys.argv[1]
    bundle = Path(sys.argv[2])

    print(f"Building OCI bundle for {image} → {bundle}")

    # Resolve hook paths early — fail fast if scripts are missing
    oci_hooks = build_oci_hooks()

    extract_rootfs(image, bundle)
    image_config = get_image_config(image)
    generate_spec(bundle)
    patch_spec(bundle, image_config, oci_hooks)

    print(f"Bundle ready. Run with: sudo runc run --bundle {bundle} <id>")
    return 0


if __name__ == "__main__":
    sys.exit(main())

