# just_enough Manifest Reference

The manifest is a YAML file that declares the complete runtime content of a container image. It is the single source of truth for what becomes the rootfs
staging directory (output). Everything in the rootfs is either declared in the manifest or mechanically required by a declared binary's ELF dependency graph.

---

## Complete Example

```yaml
version: 1

input:
  backend: buildroot
  mode: staging
  path: /path/to/buildroot/output/staging

binaries:
  - BUILDROOT/usr/bin/netcat:/usr/bin/netcat
  - BUILDROOT/usr/sbin/nginx:/usr/sbin/nginx

data:
  - BUILDROOT/etc/passwd:/etc/passwd
  - BUILDROOT/etc/nginx/nginx.conf:/etc/nginx/nginx.conf
  - ./local/config/motd:/etc/motd

directories:
  - /var/log/nginx
  - /var/run
  - /tmp

symlinks:
  - /usr/bin/netcat:/usr/bin/nc
  - /usr/lib:/lib
```

---

## Top-Level Structure

| Key | Required | Description |
|---|---|---|
| `version` | Yes | Schema version. Must be `1`. |
| `input` | Yes | Declares the build system backend and sysroot path. |
| `binaries` | No | ELF executables to include. Triggers dependency resolution. |
| `data` | No | Non-executable runtime files to copy verbatim. |
| `directories` | No | Directories to create in the staging rootfs. |
| `symlinks` | No | Symbolic links to create in the staging rootfs. |

No keys other than those listed above are permitted at the top level.

---

## `version`

```yaml
version: 1
```

Must be the integer `1`. Any other value is a validation error.

---

## `input`

Declares the build system backend that produced the sysroot. This block controls how backend path prefixes are resolved and what validation rules apply.

```yaml
input:
  backend: buildroot
  mode: staging
  path: /path/to/buildroot/output/staging
```

| Field | Required | Description |
|---|---|---|
| `backend` | Yes | The build system that produced the sysroot. See supported values below. |
| `mode` | Yes | Backend-specific operating mode. |
| `path` | Yes | Absolute path to the sysroot root. Must exist at validation time. May reference environment variables using `$(VAR_NAME)` syntax. |

### Supported Backends

| `backend` | `mode` values | Description |
|---|---|---|
| `buildroot` | `staging`, `per_package` | Buildroot output directory. `staging` uses a single unified staging tree. `per_package` uses `BR2_PER_PACKAGE_DIRECTORIES` isolation. |
| `yocto` | `sysroot` | Yocto Project sysroot. *(future)* |
| `generic` | *(none required)* | Arbitrary flat sysroot with no backend-specific behavior. *(future)* |

### Backend Path Prefix

The `input.backend` value determines the path prefix keyword used in `binaries[]` and `data[]` entries. The prefix is the backend name in uppercase.

| `backend` | Path prefix |
|---|---|
| `buildroot` | `BUILDROOT/` |
| `yocto` | `YOCTO/` |
| `generic` | `GENERIC/` |

A prefix that does not match `input.backend` uppercased is a validation error.

---

## `binaries`

Declares ELF executable entrypoints to include in the image. Each declared binary is the root of an ELF dependency walk. All required shared libraries and the ELF interpreter are resolved automatically and included in the rootfs.

```yaml
binaries:
  - BUILDROOT/usr/bin/netcat:/usr/bin/netcat
  - BUILDROOT/usr/sbin/nginx:/usr/sbin/nginx
```

### Entry Format

```
<source>:<destination>
```

| Field | Rules |
|---|---|
| `source` | Must begin with the backend prefix (e.g. `BUILDROOT/`). The remainder is resolved against `input.path`. The file must exist. |
| `destination` | Absolute path in the staging rootfs. |

### Behavior

- The binary is copied to the destination path.
- File permissions are transferred from the source, including setuid bits. Ownership is not transferred and will be normalized during OCI assembly.
- The destination is marked executable.
- The ELF `PT_INTERP` segment is read to identify the dynamic linker. The linker is added to the staging plan.
- All `DT_NEEDED` entries are resolved against `input.path` and added to the staging plan.
- Resolved libraries are scanned recursively until no new dependencies are found.
- Resolved libraries mirror their sysroot path in the output rootfs. No path flattening occurs.
- All resolved libraries are deduplicated. A library required by multiple binaries appears once.
- Any `DT_NEEDED` entry that cannot be resolved under `input.path` is a hard error.
- Parent directories of the destination are created automatically.

### What Is Not Automatic

Only ELF-based dependencies are resolved automatically. Runtime data files, configuration files, and any other path-based dependencies must be declared explicitly in `data[]`.

---

## `data`

Declares non-executable runtime files to copy verbatim into the staging rootfs. These files are not scanned for dependencies.

```yaml
data:
  - BUILDROOT/etc/passwd:/etc/passwd
  - BUILDROOT/etc/nginx/nginx.conf:/etc/nginx/nginx.conf
  - ./local/config/motd:/etc/motd
```

### Entry Format

```
<source>:<destination>
```

| Field | Rules |
|---|---|
| `source` | May begin with the backend prefix (e.g. `BUILDROOT/`) for files from the sysroot, or a relative local path (e.g. `./`) for files from the project directory. The file must exist. |
| `destination` | Absolute path in the staging rootfs. |

### Behavior

- The file is copied to the destination path verbatim.
- File permissions are transferred from the source, including setuid bits. Ownership is not transferred.
- The file is not scanned for ELF dependencies.
- Parent directories of the destination are created automatically.

---

## `directories`

Declares directories that must exist in the staging rootfs at runtime. Directories are created before any files are copied.

```yaml
directories:
  - /var/log/nginx
  - /var/run
  - /tmp
```

### Entry Format

A bare absolute path. No colon. No source reference.

### Behavior

- Directories are created in the staging rootfs using `mkdir -p` semantics.
- Created before any file copy or symlink creation.
- Must not reference the sysroot backend. There is no concept of "copying" a directory from the sysroot.

> **Note:** Parent directories for `binaries[]` and `data[]` destinations are created automatically. `directories[]` is for runtime directories that must exist but will not be populated by file copy — for example `/tmp`, `/var/run`, or `/var/log/nginx`.

---

## `symlinks`

Declares symbolic links to create in the staging rootfs. Symlinks are created after all files and directories.

```yaml
symlinks:
  - /usr/bin/netcat:/usr/bin/nc
  - /usr/lib:/lib
```

### Entry Format

```
<link_path>:<target_path>
```

| Field | Rules |
|---|---|
| `link_path` | Absolute path. The name of the symlink as it will appear in the staging rootfs. |
| `target_path` | Absolute path. The value the symlink points to. Must resolve within the staging plan. |

### Behavior

- The symlink `link_path → target_path` is created in the staging rootfs.
- `target_path` must exist within the staging plan: it must be a destination declared in `binaries[]`, `data[]`, `directories[]`, or the `link_path` of another symlink entry.
- Symlink targets must be absolute paths. Relative symlink targets are not supported.
- Must not reference the sysroot backend.

---

## Validation Rules

All validation is performed before any filesystem work begins. The first failure exits immediately with a descriptive error. No partial output is produced.

| # | Rule |
|---|---|
| V1 | `version` must be `1` |
| V2 | No unknown top-level keys are permitted |
| V3 | `input.backend` must be a known value |
| V4 | `input.mode` must be valid for the declared backend |
| V5 | `input.path` must resolve and exist |
| V6 | Backend prefix in source paths must match `input.backend` uppercased. A `YOCTO/` prefix in a `buildroot` manifest is an error. |
| V7 | Backend prefix may only appear in `binaries[]` and `data[]` source paths. A `BUILDROOT/` prefix in `directories[]` or `symlinks[]` is an error. |
| V8 | All source paths in `binaries[]` must exist under `input.path` |
| V9 | All source paths in `data[]` must exist under `input.path` or the local project path |
| V10 | All destination paths in `binaries[]` and `data[]` must be absolute |
| V11 | All entries in `directories[]` must be absolute paths |
| V12 | All `link_path` and `target_path` values in `symlinks[]` must be absolute paths |
| V13 | No duplicate destination paths across all sections combined |
| V14 | Symlink `target_path` values must resolve within the staging plan |
| V15 | Legacy variable syntax (e.g. `$(SYSROOT)`) is not accepted anywhere in the manifest |

---

## Global Constraints

**The sysroot is read-only.** The backend sysroot is never modified. `just_enough` only reads from it.

**Only `binaries[]` and `data[]` may reference the sysroot.** The `directories[]` and `symlinks[]` sections describe the staging rootfs only. Any attempt to reference the backend in those sections is a validation error.

**Fail fast. Loudly.** A manifest that does not pass all validation rules produces no output. Errors are reported with enough context to identify the offending entry and the rule it violates.

---

## Execution Order

When the manifest is valid and the staging plan is built, the tool executes in this order:

1. Create all declared directories (`directories[]`)
2. Create all auto-generated parent directories for file destinations
3. Copy all binaries (`binaries[]`) and transfer permissions
4. Copy all ELF-resolved libraries and transfer permissions
5. Copy all data files (`data[]`) and transfer permissions
6. Create all symlinks (`symlinks[]`)

This order guarantees that all destinations exist before symlinks are created and that no file copy fails due to a missing parent directory.
