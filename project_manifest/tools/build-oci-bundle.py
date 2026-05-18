#!/usr/bin/env python3
"""
build-oci-bundle.py: Extract a Docker image into an OCI bundle for runc.
Creates a bundle directory containing rootfs/ and a config.json with
eBPF hooks injected, ready for direct invocation via runc run.

Usage:
    python3 build-oci-bundle.py <image:tag> <bundle-dir>
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HOOKS_PATH = Path("/usr/local/bin")

OCI_HOOKS = {
    "createRuntime": [{
        "path": str(HOOKS_PATH / "attach-ebpf-probe"),
        "args": ["attach-ebpf-probe"],
        "timeout": 5,
    }],
    "poststop": [{
        "path": str(HOOKS_PATH / "detach-ebpf-probe"),
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


def patch_spec(bundle: Path, image_config: dict) -> None:
    config_path = bundle / "config.json"
    config = json.loads(config_path.read_text())

    # Disable terminal allocation — CI environments have no TTY
    config["process"]["terminal"] = False

    # Allow writes to rootfs — unbound needs to write /var/run/unbound.pid
    config["root"]["readonly"] = False

    # Add capabilities unbound requires
    # CAP_SYS_CHROOT  — unbound chroots to /etc/unbound for privilege separation
    # CAP_SYS_RESOURCE — setrlimit for increasing file descriptor limits
    # CAP_SETUID/SETGID — dropping from root to unbound user at runtime
    # CAP_NET_BIND_SERVICE — binding to port 53
    required_caps = [
        "CAP_SYS_CHROOT",
        "CAP_SYS_RESOURCE",
        "CAP_SETUID",
        "CAP_SETGID",
        "CAP_NET_BIND_SERVICE",
    ]
    # Ambient deliberately excluded — runner doesn't permit raising it
    # and unbound handles privilege drop internally
    for cap_set in ("bounding", "effective", "permitted"):
        existing = config["process"]["capabilities"].setdefault(cap_set, [])
        for cap in required_caps:
            if cap not in existing:
                existing.append(cap)

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
        print(f"  process args set to: {args}")

    # Carry over environment variables
    env = image_config.get("Env") or []
    if env:
        config["process"]["env"] = env

    # Set working directory
    workdir = image_config.get("WorkingDir") or "/"
    config["process"]["cwd"] = workdir

    # Inject eBPF lifecycle hooks
    config.setdefault("hooks", {})
    for hook_type, hook_list in OCI_HOOKS.items():
        existing = config["hooks"].setdefault(hook_type, [])
        existing.extend(hook_list)
    print(f"  hooks injected: {list(OCI_HOOKS.keys())}")

    # Atomic write
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

    extract_rootfs(image, bundle)

    image_config = get_image_config(image)

    generate_spec(bundle)
    patch_spec(bundle, image_config)

    print(f"Bundle ready. Run with: sudo runc run --bundle {bundle} <id>")
    return 0


if __name__ == "__main__":
    sys.exit(main())

