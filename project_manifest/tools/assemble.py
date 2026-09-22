#!/usr/bin/env python3

import os
import shutil
import sys
from pathlib import Path, PurePosixPath

import yaml
from elftools.elf.dynamic import DynamicSection
from elftools.elf.elffile import ELFFile
from elftools.elf.segments import InterpSegment


class ManifestError(Exception):
    """Raised for any fatal problem encountered while assembling the rootfs
    (a malformed manifest entry, a missing source file, etc). Caught only in
    main() and translated into a CLI exit; everything below main() — including
    build_rootfs() — lets it propagate, so tests can assert on it directly
    with pytest.raises(ManifestError) instead of the process exiting."""


def fail(msg):
    raise ManifestError(msg)


def load_manifest(path):
    with open(path) as f:
        return yaml.safe_load(f)


def ensure_abs(path):
    if not path.startswith("/"):
        fail(f"Path must be absolute: {path}")


def resolve_source(src, sysroot):
    """
    Resolve a manifest source path to an absolute filesystem path.

    BUILDROOT/ paths are resolved directly against the flat rootfs sysroot
    (either output/target/ locally or the extracted kitchen-sink tarball in CI).

    Local paths beginning with ./ are resolved relative to the working directory.
    """
    if src.startswith("BUILDROOT/"):
        rel = src[len("BUILDROOT/"):]
        return Path(sysroot) / rel
    elif src.startswith("./"):
        return Path(src).resolve()
    else:
        fail(f"Invalid source path: {src}")


def build_symlink_remap(symlinks):
    """
    Parse the manifest symlinks list into a {link_path: target_path} dict.

    During file copy, any destination whose prefix matches a declared link_path
    is rewritten to use the target_path instead. This ensures that files land
    in the real directory rather than in a path that will later become a symlink.

    Example: link=/usr/lib, target=/lib, dest=/usr/lib/libssl.so.3
             -> remapped to /lib/libssl.so.3

    This prevents the conflict where copy_libs populates /usr/lib/ as a real
    directory and the later symlink step then fails trying to replace it.
    """
    remap = {}
    for entry in symlinks:
        target, link = entry.split(":", 1)
        remap[link.rstrip("/")] = target.rstrip("/")
    return remap


def remap_dest(dst_path, remap):
    """
    Rewrite dst_path by replacing any matching link_path prefix with its
    target_path. Longest prefix wins to handle nested cases correctly.

    Returns the (possibly rewritten) absolute destination path.
    """
    p = PurePosixPath(dst_path)
    best_match = None
    for link, target in remap.items():
        link_p = PurePosixPath(link)
        try:
            rel = p.relative_to(link_p)
            if best_match is None or len(link) > len(best_match[0]):
                best_match = (link, str(PurePosixPath(target) / rel))
        except ValueError:
            continue
    return best_match[1] if best_match else dst_path


def copy_file(src, dst_root, dst_path, remap=None):
    ensure_abs(dst_path)
    if remap:
        dst_path = remap_dest(dst_path, remap)
    dst = dst_root / dst_path.lstrip("/")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def copy_tree(src, dst_root, dst_path, remap=None):
    """
    Recursively copy a directory tree into the staging rootfs.

    The remap table is applied once to the top-level destination path, then
    the directory's full contents are mirrored beneath the (possibly
    remapped) destination. This gives the same result as remapping each file
    individually for the common case (a backend-prefixed directory landing
    under a path whose prefix is itself a declared symlink target, e.g.
    /usr/lib -> /lib), without re-running prefix matching for every file.

    Symlinks within the tree are preserved verbatim (not followed and not
    re-resolved), consistent with how resolved library soname symlinks are
    handled in copy_lib_symlinks. File permissions, including setuid/setgid
    bits, are preserved via copy2.

    Note: unlike binaries[], directory trees copied via data[] are not
    scanned for ELF dependencies. Any shared libraries required by files
    inside the tree (e.g. compiled extension modules) must already be
    present in the rootfs via a declared binaries[] entry or another
    data[] entry.
    """
    ensure_abs(dst_path)
    if remap:
        dst_path = remap_dest(dst_path, remap)
    dst = dst_root / dst_path.lstrip("/")
    shutil.copytree(src, dst, symlinks=True, copy_function=shutil.copy2,
                    dirs_exist_ok=True)


def get_elf_needed(filepath):
    """
    Extract DT_NEEDED library names and the PT_INTERP interpreter path
    directly from an ELF binary using pyelftools.

    Returns a list of soname strings (e.g. 'libc.so.6') plus, if present,
    the interpreter's sysroot-absolute path (e.g. '/lib64/ld-linux-x86-64.so.2').
    Non-ELF or corrupted files are skipped gracefully.
    """
    needed = []
    try:
        with open(filepath, 'rb') as f:
            elffile = ELFFile(f)
            for segment in elffile.iter_segments():
                if isinstance(segment, InterpSegment):
                    needed.append(segment.get_interp_name())
            for section in elffile.iter_sections():
                if isinstance(section, DynamicSection):
                    for tag in section.iter_tags():
                        if tag.entry.d_tag == 'DT_NEEDED':
                            needed.append(tag.needed)
    except Exception:
        pass
    return needed


def resolve_elf_deps(sysroot, binary):
    """
    Recursively resolve the shared-library dependency closure of `binary`
    using pyelftools, replacing the previous `lddtree -l --root sysroot` call.

    Each DT_NEEDED soname is located under the sysroot's standard library
    directories (via find_lib_in_sysroot) and then walked itself, since a
    shared library can have its own DT_NEEDED entries (e.g. libcrypto ->
    libz). PT_INTERP entries are sysroot-absolute paths and are resolved
    directly against the sysroot rather than searched for.

    Returns a list of absolute host-filesystem path strings, mirroring
    lddtree -l's output format (including that an entry may be a soname
    symlink rather than the real file) so that copy_libs can consume it
    unchanged.
    """
    resolved = []
    visited_paths = set()

    def _walk(elf_path):
        for name in get_elf_needed(elf_path):
            if name.startswith("/"):
                # PT_INTERP entries are already sysroot-absolute paths.
                lib_path = sysroot / name.lstrip("/")
                if not lib_path.exists():
                    fail(f"Missing interpreter: {lib_path}")
            else:
                lib_path = find_lib_in_sysroot(sysroot, name)

            # Dedupe by resolved path rather than by name: a library like
            # glibc's libc.so.6 can reference the same interpreter via both
            # an embedded PT_INTERP and a bare DT_NEEDED soname, which are
            # different strings but must not be walked/copied twice.
            key = str(lib_path)
            if key in visited_paths:
                continue
            visited_paths.add(key)

            resolved.append(key)
            _walk(lib_path)

    _walk(Path(binary))
    return resolved


def copy_lib_symlinks(sysroot, dst_root, lib_path, remap=None):
    """
    Recreate all symlinks in the sysroot directory that resolve (directly or
    transitively) to lib_path.

    lddtree -l returns only the real library files, not the soname symlinks
    that sit alongside them (e.g. libssl.so.3 -> libssl.so.3.0.2). Without
    these symlinks the dynamic linker cannot find the library at runtime,
    because DT_NEEDED entries reference the soname, not the versioned filename.

    We walk the same directory as the library, find every symlink whose fully
    resolved target matches the real library file, and recreate it in the
    output rootfs using the original (possibly relative) link target so that
    the symlink relationship is preserved faithfully.

    The remap table is applied to the symlink destination path so that soname
    symlinks land alongside their real file after any path remapping.
    """
    real_lib = lib_path.resolve()
    for entry in lib_path.parent.iterdir():
        if not entry.is_symlink():
            continue
        try:
            if entry.resolve() != real_lib:
                continue
        except OSError:
            # Dangling symlink in the sysroot -- skip it.
            continue

        rel = entry.relative_to(sysroot)
        dst_path = "/" + str(rel)
        if remap:
            dst_path = remap_dest(dst_path, remap)
        dst_link = dst_root / dst_path.lstrip("/")
        dst_link.parent.mkdir(parents=True, exist_ok=True)
        if dst_link.exists() or dst_link.is_symlink():
            dst_link.unlink()
        # Preserve the original link target verbatim (may be relative).
        os.symlink(os.readlink(entry), dst_link)


_SYSROOT_LIB_DIRS = ["lib", "usr/lib", "lib64", "usr/lib64", "usr/lib/samba"]


def find_lib_in_sysroot(sysroot, soname):
    """
    Resolve a bare soname (e.g. 'libc.so.6') to its full path in the sysroot.

    lddtree -l returns full sysroot-prefixed paths for most libraries, but
    outputs bare sonames for some dependencies when processing shared libraries
    rather than executables. Without this fallback those entries hit a false
    'missing library' error even though the file is present in the sysroot.
    """
    for d in _SYSROOT_LIB_DIRS:
        candidate = sysroot / d / soname
        if candidate.exists():
            return candidate
    fail(f"Cannot find library '{soname}' under {sysroot}")


def copy_libs(sysroot, dst_root, binary_src, remap=None):
    """
    Resolve and copy all shared library dependencies of binary_src.

    Dependency resolution is rooted at the flat rootfs sysroot (output/target/
    or an equivalent extracted tarball). All library lookups and soname
    symlink reconstruction are performed against this single directory.
    """
    libs = resolve_elf_deps(sysroot, binary_src)

    for lib in libs:
        p = Path(lib)

        # resolve_elf_deps returns full sysroot-prefixed paths, but guard
        # against a bare soname (e.g. 'libc.so.6') the same way the old
        # lddtree-based path did, in case a future caller passes one in.
        if not p.is_absolute():
            p = find_lib_in_sysroot(sysroot, lib)
        elif not p.exists():
            fail(f"Missing library: {p}")

        # lddtree may return a soname symlink path (e.g. libsodium.so.23)
        # rather than the real file (libsodium.so.23.3.0). Always resolve to
        # the real file so the actual content lands at its canonical versioned
        # path. Without this, copy_lib_symlinks would later overwrite the
        # copied file with a symlink, leaving a dangling link and no library.
        real_p = p.resolve()
        rel = real_p.relative_to(sysroot)
        dst_path = "/" + str(rel)
        if remap:
            dst_path = remap_dest(dst_path, remap)

        dst = dst_root / dst_path.lstrip("/")
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(real_p, dst)

        # Recreate any soname / major-version symlinks that point to this
        # library so the dynamic linker can resolve DT_NEEDED entries at
        # runtime (e.g. libssl.so.3 -> libssl.so.3.0.2).
        copy_lib_symlinks(sysroot, dst_root, real_p, remap)


def materialize_directories(manifest, out_dir):
    """Create every declared directory[] entry under out_dir."""
    for d in manifest.get("directories", []):
        ensure_abs(d)
        (out_dir / d.lstrip("/")).mkdir(parents=True, exist_ok=True)


def materialize_binaries(manifest, sysroot, out_dir, remap=None):
    """Copy every declared binaries[] entry, plus its resolved shared-library
    dependency closure, into out_dir."""
    for entry in manifest.get("binaries", []):
        src, dst = entry.split(":", 1)
        src_path = resolve_source(src, sysroot)
        if not src_path.exists():
            fail(f"Binary not found: {src_path}")
        copy_file(src_path, out_dir, dst, remap)
        copy_libs(sysroot, out_dir, src_path, remap)


def materialize_data(manifest, sysroot, out_dir, remap=None):
    """
    Copy every declared data[] entry into out_dir.

    Entries may reference either a single file or a directory. Directories
    are copied recursively, preserving their internal structure, symlinks,
    and permissions. Directory trees are not scanned for ELF dependencies.
    """
    for entry in manifest.get("data", []):
        if ":" in entry:
            src, dst = entry.split(":", 1)
        else:
            # No destination given: mirror the sysroot path verbatim.
            # e.g. BUILDROOT/etc/ssl/openssl.cnf -> /etc/ssl/openssl.cnf
            src = entry
            for prefix in ("BUILDROOT/", "YOCTO/", "GENERIC/"):
                if src.startswith(prefix):
                    dst = "/" + src[len(prefix):]
                    break
            else:
                fail(f"Cannot infer destination for data entry with no prefix: {entry}")

        src_path = resolve_source(src, sysroot)
        if not src_path.exists():
            fail(f"Data source not found: {src_path}")

        if src_path.is_dir():
            copy_tree(src_path, out_dir, dst, remap)
        else:
            copy_file(src_path, out_dir, dst, remap)


def materialize_symlinks(manifest, out_dir):
    """
    Create every declared symlinks[] entry inside out_dir.

    Entry format is <target>:<link_path>, matching ln -s <target> <link>
    semantics. Both paths are container-absolute in the manifest, and the
    target is written into the symlink verbatim, still absolute (e.g.
    target=/usr/bin, link=/bin -> /bin is a symlink to the literal string
    "/usr/bin", not a relative "usr/bin").

    This resolves correctly once the rootfs is running as a container, since
    the container has its own root and "/usr/bin" means the container's
    /usr/bin. It does NOT resolve correctly against the staging directory
    on the host: any host-side tooling that follows the symlink while
    out_dir is just a directory on disk (packaging scripts, tar, manual
    inspection) will jump to the host's real /usr/bin instead of
    out_dir/usr/bin.
    """
    for entry in manifest.get("symlinks", []):
        target, link = entry.split(":", 1)
        ensure_abs(link)
        ensure_abs(target)
        link_path = out_dir / link.lstrip("/")
        link_path.parent.mkdir(parents=True, exist_ok=True)
        if link_path.exists() or link_path.is_symlink():
            link_path.unlink()
        os.symlink(target, link_path)


def build_rootfs(manifest, sysroot, out_dir):
    """
    Assemble a complete staging rootfs at out_dir from manifest, rooted
    against sysroot.

    Wipes and recreates out_dir, then materializes directories, binaries
    (+ their resolved library closures), data entries, and symlinks, in
    that order. This is the full pipeline main() used to run inline; it
    takes no CLI or environment state, so it can be called directly from
    tests with an in-memory manifest dict and a tmp_path sysroot/out_dir.
    """
    if not sysroot.exists():
        fail(f"Sysroot does not exist: {sysroot}")

    # Build a path-remap table from the declared symlinks so that file copies
    # can redirect destinations before any symlink is created on disk.
    # e.g. /usr/lib -> /lib means libraries are written to /lib/ directly,
    # leaving /usr/lib free to be created as a symlink later.
    remap = build_symlink_remap(manifest.get("symlinks", []))

    # Clean output
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    materialize_directories(manifest, out_dir)
    materialize_binaries(manifest, sysroot, out_dir, remap)
    materialize_data(manifest, sysroot, out_dir, remap)
    materialize_symlinks(manifest, out_dir)

    print(f"Rootfs built at: {out_dir}")


def main():
    if len(sys.argv) != 3:
        print("Usage: assemble.py <manifest.yaml> <output_dir>")
        sys.exit(1)

    manifest_path = sys.argv[1]
    out_dir = Path(sys.argv[2]).resolve()
    manifest = load_manifest(manifest_path)

    # SYSROOT environment variable overrides input.path. This allows the same
    # manifest to be used locally (pointing at output/target/) and in CI
    # (pointing at an extracted kitchen-sink tarball) without editing the file.
    sysroot_env = os.environ.get("SYSROOT")
    if sysroot_env:
        sysroot = Path(sysroot_env).resolve()
    else:
        sysroot = Path(manifest["input"]["path"]).resolve()

    # build_rootfs() and everything it calls raise ManifestError on any fatal
    # problem rather than exiting directly. main() is the only place that
    # catches it, so build_rootfs() stays exception-clean for callers (tests)
    # that want to assert on the failure instead of losing the process.
    try:
        build_rootfs(manifest, sysroot, out_dir)
    except ManifestError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

