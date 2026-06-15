#!/usr/bin/env python3

import os
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath

import yaml


def die(msg):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def load_manifest(path):
    with open(path) as f:
        return yaml.safe_load(f)


def ensure_abs(path):
    if not path.startswith("/"):
        die(f"Path must be absolute: {path}")


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
        die(f"Invalid source path: {src}")


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


def run_lddtree(sysroot, binary):
    # convert absolute sysroot path -> relative path inside sysroot
    rel = Path(binary).relative_to(sysroot)
    cmd = ["lddtree", "-l", "--root", str(sysroot), "/" + str(rel)]
    out = subprocess.check_output(cmd, text=True)
    return [line.strip() for line in out.splitlines() if line.strip()]


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


_SYSROOT_LIB_DIRS = ["lib", "usr/lib", "lib64", "usr/lib64"]


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
    die(f"Cannot find library '{soname}' under {sysroot}")


def copy_libs(sysroot, dst_root, binary_src, remap=None):
    """
    Resolve and copy all shared library dependencies of binary_src.

    lddtree is rooted at the flat rootfs sysroot (output/target/ or an
    equivalent extracted tarball). All library lookups and soname symlink
    reconstruction are performed against this single directory.
    """
    libs = run_lddtree(sysroot, binary_src)

    for lib in libs:
        p = Path(lib)

        # lddtree outputs full sysroot-prefixed paths for executables but may
        # emit bare sonames (e.g. 'libc.so.6') when processing shared libraries.
        # Resolve bare names against the sysroot before proceeding.
        if not p.is_absolute():
            p = find_lib_in_sysroot(sysroot, lib)
        elif not p.exists():
            die(f"Missing library: {p}")

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

    if not sysroot.exists():
        die(f"Sysroot does not exist: {sysroot}")

    # Build a path-remap table from the declared symlinks so that file copies
    # can redirect destinations before any symlink is created on disk.
    # e.g. /usr/lib -> /lib means libraries are written to /lib/ directly,
    # leaving /usr/lib free to be created as a symlink later.
    remap = build_symlink_remap(manifest.get("symlinks", []))

    # Clean output
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    # 1. directories
    for d in manifest.get("directories", []):
        ensure_abs(d)
        (out_dir / d.lstrip("/")).mkdir(parents=True, exist_ok=True)

    # 2. binaries + libs
    for entry in manifest.get("binaries", []):
        src, dst = entry.split(":", 1)
        src_path = resolve_source(src, sysroot)
        if not src_path.exists():
            die(f"Binary not found: {src_path}")
        copy_file(src_path, out_dir, dst, remap)
        copy_libs(sysroot, out_dir, src_path, remap)

    # 3. data
    # Entries may reference either a single file or a directory. Directories
    # are copied recursively, preserving their internal structure, symlinks,
    # and permissions. Directory trees are not scanned for ELF dependencies.
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
                die(f"Cannot infer destination for data entry with no prefix: {entry}")

        src_path = resolve_source(src, sysroot)
        if not src_path.exists():
            die(f"Data source not found: {src_path}")

        if src_path.is_dir():
            copy_tree(src_path, out_dir, dst, remap)
        else:
            copy_file(src_path, out_dir, dst, remap)

    # 4. symlinks
    # Entry format is <target>:<link_path>, matching ln -s <target> <link> semantics.
    # Both paths are container-absolute in the manifest. We convert the target
    # to a relative path at materialization time so the symlink is self-contained
    # within the staging rootfs and does not escape to the host filesystem.
    #
    # Example: target=/usr/bin, link=/bin
    #   link directory = /  ->  relative target = usr/bin  (not /usr/bin)
    #
    # Example: target=/lib, link=/usr/lib
    #   link directory = /usr  ->  relative target = ../lib
    for entry in manifest.get("symlinks", []):
        target, link = entry.split(":", 1)
        ensure_abs(link)
        ensure_abs(target)
        link_path = out_dir / link.lstrip("/")
        link_path.parent.mkdir(parents=True, exist_ok=True)
        if link_path.exists() or link_path.is_symlink():
            link_path.unlink()
        os.symlink(target, link_path)

    print(f"Rootfs built at: {out_dir}")


if __name__ == "__main__":
    main()

