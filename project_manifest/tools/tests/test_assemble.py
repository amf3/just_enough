import os
import subprocess
from pathlib import Path

import pytest

import assemble


# ---------------------------------------------------------------------------
# resolve_elf_deps
# ---------------------------------------------------------------------------

def test_resolve_elf_deps_finds_every_dependency(flat_sysroot):
    target = flat_sysroot / "usr" / "bin" / "python3"
    libs = assemble.resolve_elf_deps(flat_sysroot, target)

    assert libs, "expected at least one resolved dependency"
    for lib in libs:
        assert Path(lib).exists()
        assert str(flat_sysroot) in lib


def test_resolve_elf_deps_has_no_duplicates(flat_sysroot):
    # Regression test: a library can reference the same interpreter via both
    # an embedded PT_INTERP and a bare DT_NEEDED soname (different strings,
    # same file) — these must be deduped by resolved path.
    target = flat_sysroot / "usr" / "bin" / "python3"
    libs = assemble.resolve_elf_deps(flat_sysroot, target)
    assert len(libs) == len(set(libs))


def test_resolve_elf_deps_includes_interpreter(flat_sysroot):
    target = flat_sysroot / "usr" / "bin" / "python3"
    libs = assemble.resolve_elf_deps(flat_sysroot, target)
    assert any("ld-linux" in lib for lib in libs)


def test_resolve_elf_deps_includes_libc(flat_sysroot):
    target = flat_sysroot / "usr" / "bin" / "python3"
    libs = assemble.resolve_elf_deps(flat_sysroot, target)
    assert any("libc.so" in lib for lib in libs)


# ---------------------------------------------------------------------------
# build_rootfs — happy path
# ---------------------------------------------------------------------------

def test_build_rootfs_copies_binary_and_its_deps(flat_sysroot, tmp_path):
    manifest = {
        "input": {"path": str(flat_sysroot)},
        "directories": ["/usr/bin"],
        "binaries": ["BUILDROOT/usr/bin/python3:/usr/bin/python3"],
        "symlinks": ["/lib:/usr/lib"],
    }
    out_dir = tmp_path / "rootfs"

    assemble.build_rootfs(manifest, flat_sysroot, out_dir)

    copied = out_dir / "usr" / "bin" / "python3"
    assert copied.exists()
    assert os.access(copied, os.X_OK)


def test_build_rootfs_recreates_soname_symlinks(flat_sysroot, tmp_path):
    manifest = {
        "input": {"path": str(flat_sysroot)},
        "binaries": ["BUILDROOT/usr/bin/python3:/usr/bin/python3"],
    }
    out_dir = tmp_path / "rootfs"
    assemble.build_rootfs(manifest, flat_sysroot, out_dir)

    # Every soname symlink present in the fixture's lib/ must be recreated
    # in the output, pointing at a real file that actually exists there.
    src_symlinks = [e for e in (flat_sysroot / "lib").iterdir() if e.is_symlink()]
    assert src_symlinks, "fixture should contain at least one soname symlink"
    for entry in src_symlinks:
        out_link = out_dir / "lib" / entry.name
        assert out_link.is_symlink()
        assert (out_link.parent / os.readlink(out_link)).exists()


def test_build_rootfs_output_binary_actually_runs(flat_sysroot, tmp_path):
    """
    The strongest assertion available: don't just check the files exist —
    actually exec the copied interpreter against the copied libraries (via
    an explicit --library-path, since we're not chrooting) and confirm the
    dynamic linker can resolve every dependency assemble.py copied.
    """
    manifest = {
        "input": {"path": str(flat_sysroot)},
        "binaries": ["BUILDROOT/usr/bin/python3:/usr/bin/python3"],
    }
    out_dir = tmp_path / "rootfs"
    assemble.build_rootfs(manifest, flat_sysroot, out_dir)

    interp = next((out_dir / "lib64").glob("ld-linux*"))
    result = subprocess.run(
        [
            str(interp), "--library-path", str(out_dir / "lib"),
            str(out_dir / "usr" / "bin" / "python3"), "-c", "print('ok')",
        ],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"


def test_symlink_remap_redirects_library_destination(flat_sysroot, tmp_path):
    """
    A /usr/lib -> /lib manifest symlink must redirect copied libraries
    straight to lib/, leaving usr/lib free to be created as a real symlink
    afterward instead of colliding with a directory copy_libs already wrote.
    """
    manifest = {
        "input": {"path": str(flat_sysroot)},
        "binaries": ["BUILDROOT/usr/bin/python3:/usr/bin/python3"],
        "symlinks": ["/lib:/usr/lib"],
    }
    out_dir = tmp_path / "rootfs"
    assemble.build_rootfs(manifest, flat_sysroot, out_dir)

    assert (out_dir / "usr" / "lib").is_symlink()
    assert any((out_dir / "lib").iterdir())


# ---------------------------------------------------------------------------
# materialize_data
# ---------------------------------------------------------------------------

def test_materialize_data_copies_single_file_with_explicit_dest(flat_sysroot, tmp_path):
    manifest = {"data": ["BUILDROOT/usr/bin/python3:/etc/marker"]}
    out_dir = tmp_path / "rootfs"
    out_dir.mkdir()
    assemble.materialize_data(manifest, flat_sysroot, out_dir)
    assert (out_dir / "etc" / "marker").exists()


def test_materialize_data_infers_destination_from_prefix(flat_sysroot, tmp_path):
    manifest = {"data": ["BUILDROOT/usr/bin/python3"]}
    out_dir = tmp_path / "rootfs"
    out_dir.mkdir()
    assemble.materialize_data(manifest, flat_sysroot, out_dir)
    assert (out_dir / "usr" / "bin" / "python3").exists()


def test_materialize_data_copies_directory_tree(flat_sysroot, tmp_path):
    manifest = {"data": ["BUILDROOT/lib:/copied-lib"]}
    out_dir = tmp_path / "rootfs"
    out_dir.mkdir()
    assemble.materialize_data(manifest, flat_sysroot, out_dir)

    src_names = {e.name for e in (flat_sysroot / "lib").iterdir()}
    dst_names = {e.name for e in (out_dir / "copied-lib").iterdir()}
    assert src_names == dst_names


# ---------------------------------------------------------------------------
# directories / symlinks in isolation (no binary involved)
# ---------------------------------------------------------------------------

def test_materialize_directories_only(tmp_path):
    manifest = {"directories": ["/etc", "/var/log"]}
    assemble.materialize_directories(manifest, tmp_path)
    assert (tmp_path / "etc").is_dir()
    assert (tmp_path / "var" / "log").is_dir()


def test_materialize_symlinks_only(tmp_path):
    manifest = {"symlinks": ["/usr/bin:/bin"]}
    assemble.materialize_symlinks(manifest, tmp_path)
    assert (tmp_path / "bin").is_symlink()
    # NOTE: materialize_symlinks' docstring claims the target is converted to
    # a relative path (e.g. "usr/bin", not "/usr/bin") so the symlink stays
    # self-contained within the staging rootfs. The current implementation
    # does not actually do this conversion — os.symlink() is called with the
    # raw absolute target. This assertion documents the *actual* behavior;
    # see the conversation for the discrepancy against the docstring.
    assert os.readlink(tmp_path / "bin") == "/usr/bin"


# ---------------------------------------------------------------------------
# error paths — ManifestError propagates instead of exiting the process
# ---------------------------------------------------------------------------

def test_build_rootfs_raises_on_missing_binary(flat_sysroot, tmp_path):
    manifest = {
        "input": {"path": str(flat_sysroot)},
        "binaries": ["BUILDROOT/usr/bin/does-not-exist:/usr/bin/nope"],
    }
    with pytest.raises(assemble.ManifestError, match="Binary not found"):
        assemble.build_rootfs(manifest, flat_sysroot, tmp_path / "rootfs")


def test_build_rootfs_raises_on_missing_sysroot(tmp_path):
    with pytest.raises(assemble.ManifestError, match="Sysroot does not exist"):
        assemble.build_rootfs({}, tmp_path / "nope", tmp_path / "rootfs")


def test_build_rootfs_raises_on_unresolvable_dependency(flat_sysroot, tmp_path):
    # Delete a real dependency out of the fixture sysroot so resolution fails.
    for entry in (flat_sysroot / "lib").glob("libc.so*"):
        entry.unlink()

    manifest = {
        "input": {"path": str(flat_sysroot)},
        "binaries": ["BUILDROOT/usr/bin/python3:/usr/bin/python3"],
    }
    with pytest.raises(assemble.ManifestError, match="Cannot find library"):
        assemble.build_rootfs(manifest, flat_sysroot, tmp_path / "rootfs")
