import os
import shutil
import subprocess
from pathlib import Path

import pytest


def _ldd_resolved_paths(binary):
    """
    Real, host-resolved absolute paths for every shared library `ldd`
    reports for binary. Deliberately uses the system `ldd`, not
    assemble.resolve_elf_deps, to build the fixture: if we used the code
    under test to build its own test data, a bug in dependency resolution
    could hide itself.
    """
    out = subprocess.check_output(["ldd", str(binary)], text=True)
    paths = []
    for line in out.splitlines():
        line = line.strip()
        if "=>" in line:
            rhs = line.split("=>", 1)[1].strip()
            path = rhs.split(" ")[0]
        elif line.startswith("/"):
            path = line.split(" ")[0]
        else:
            continue
        if path and os.path.exists(path):
            paths.append(path)
    return paths


@pytest.fixture
def flat_sysroot(tmp_path):
    """
    A minimal flat Buildroot-style sysroot built around the real `python3`
    interpreter already on PATH - a dependency the project already has, so
    nothing about the target binary or its libraries is fabricated or
    mocked.

    Layout matches what assemble.py expects from a Buildroot kitchen-sink
    rootfs: real library files plus their soname symlinks live flat under
    lib/ and lib64/, and the target binary sits at a BUILDROOT/-style path
    (usr/bin/python3).
    """
    python3 = shutil.which("python3")
    if python3 is None:
        pytest.skip("python3 not found on PATH")
    python3 = Path(python3).resolve()

    sysroot = tmp_path / "sysroot"
    (sysroot / "usr" / "bin").mkdir(parents=True)
    (sysroot / "lib").mkdir()
    (sysroot / "lib64").mkdir()

    shutil.copy2(python3, sysroot / "usr" / "bin" / "python3")

    for path in _ldd_resolved_paths(python3):
        real = Path(os.path.realpath(path))
        dest_dir = sysroot / "lib64" if "ld-linux" in path else sysroot / "lib"

        real_dst = dest_dir / real.name
        if not real_dst.exists():
            shutil.copy2(real, real_dst)

        soname_dst = dest_dir / Path(path).name
        if soname_dst != real_dst and not soname_dst.exists():
            os.symlink(real.name, soname_dst)

    return sysroot
