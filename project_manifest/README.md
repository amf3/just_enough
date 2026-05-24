# Project Manifest

## Overview

The idea behind Project Manifest is to use Buildroot as an artifact generator as it does a great job at
providing the tool chain and patching applications.  Project Manifest uses a manifest file to consume Buildroot
output and create a appliance-like container image.  The manifest will allow one to combine Buildroot artifacts
into a single container image.  In short, you can think of this project as applying package manager concepts
like RPM spec files or DPKG control files to containers.  The build process happens in several stages.  

* The first stage is to create Buildroot artifacts. 
* The second stage runs an assemble script to read the supplied manifest file and copy Buildroot artifacts into a staging directory.
* The third stage uses external OCI compatible tooling like Docker Buildx or Buildah to generate a local container image by consuming content in the staging directory.
* The fourth stage is intended to push the local image to container image repository along with any attestations or SBOMs.

## Build process

### Create the Buildroot artifact

The top level [README.md](../README.md) file has descriptions for creating the Buildroot build artifact.  These can be either built locally by installing compilers
and other developer tooling, or within a [Multipass VM](../build_with_mulitpass/README.md) or a [Docker container](../build_with_docker/README.md). The Multipass
or Docker build environments simplify setting up the Buildroot environment, but obviously require either Multipass or Docker be installed locally. If building on MacOS
using the Multipass environment works better due to IO performance with Docker Desktop on MacOS.  All methods have a dependency on the Make command.

### Run the assemble script

The [assemble script](./tools/assemble.py) has a dependency on the lddtree command which comes from the pax-utils package on Ubuntu and is written in Python, so assemble.py 
needs a Python interpreter to run.  These requirements already exist if using the Multipass or Docker environments.

For input, assemble.py requires the Buildroot artifact directory a manifest file and a staging directory. The [manifest file format](./docs/manifest.md) is 
documented for creating new container images.   

Run the assemble.py script. This example is using the build_with_docker environment.  The Docker container does a bind mount to the local filesystem, so 
changes are visible outside of the Docker environment. 

```shell
# A simple Help statement
ubuntu@b827da484e2b:/app$ ./project_manifest/tools/assemble.py --help
Usage: assemble.py <manifest.yaml> <output_dir>

# Command fails as Buildroot output is not found
ubuntu@b827da484e2b:/app$ ./project_manifest/tools/assemble.py ./project_manifest/unbound_dns/container_def.yml ./my_staging_dir
ERROR: Sysroot does not exist: /home/ubuntu/just_enough/staging

# We can override defaults by setting a SYSROOT environment variable
ubuntu@b827da484e2b:/app$ ls ./staging/
bin  dev  etc  lib  lib64  media  mnt  opt  proc  root  run  sbin  sys  tmp  usr  var
ubuntu@b827da484e2b:/app$ export SYSROOT=$PWD/staging/
ubuntu@b827da484e2b:/app$ ./project_manifest/tools/assemble.py ./project_manifest/unbound_dns/container_def.yml ./my_staging_dir
Rootfs built at: /app/my_staging_dir

```

### Create the OCI image

Now that our container image content is staged, we can use standard container tooling to create the container image. In this example I'll use Docker Buildx.
Docker commands will be ran from the host environment.  Including Docker within a Docker build environment felt redundant as the host OS already has Docker installed. 
Alternative tooling like Buildah could also be used.

```shell
# Contents of our new container image staging directory
adam@phanpy:~/work/just_enough$ ls -l my_staging_dir/
total 16
lrwxrwxrwx 1 adam adam    8 May 23 00:16 bin -> /usr/bin
drwxr-xr-x 4 adam adam 4096 May 23 00:16 etc
drwxr-xr-x 2 adam adam 4096 May 23 00:16 lib
lrwxrwxrwx 1 adam adam    4 May 23 00:16 lib64 -> /lib
lrwxrwxrwx 1 adam adam    9 May 23 00:16 sbin -> /usr/sbin
drwxr-xr-x 4 adam adam 4096 May 23 00:16 usr
drwxr-xr-x 4 adam adam 4096 May 23 00:16 var

# Create the container image ...
adam@phanpy:~/work/just_enough$ docker build --tag mycontainer:latest  --build-arg STAGING_DIR=my_staging_dir --file ./project_manifest/unbound_dns/Dockerfile . 
[+] Building 0.6s (5/5) FINISHED                                                                                                                                             docker:default
 => [internal] load build definition from Dockerfile                                                                                                                                   0.1s
 => => transferring dockerfile: 786B                                                                                                                                                   0.0s
 => [internal] load .dockerignore                                                                                                                                                      0.0s
 => => transferring context: 2B                                                                                                                                                        0.0s
 => [internal] load build context                                                                                                                                                      0.1s
 => => transferring context: 2.80kB                                                                                                                                                    0.0s
 => CACHED [1/1] COPY --chown=100:100 my_staging_dir/ /                                                                                                                                0.0s
 => exporting to image                                                                                                                                                                 0.0s
 => => exporting layers                                                                                                                                                                0.0s
 => => writing image sha256:0ccd2b9e2abb037fab766b2516e8f3b1a3ec936cd326e66b9965820fe9c0f3e8                                                                                           0.0s
 => => naming to docker.io/library/mycontainer:latest

# List the new container 
adam@phanpy:~/work/just_enough$ docker images mycontainer
                                                                                                                                                                        i Info →   U  In Use
IMAGE                ID             DISK USAGE   CONTENT SIZE   EXTRA
mycontainer:latest   0ccd2b9e2abb       23.4MB             0B    

```

### Validate the new container image

Using lddtree to perform [static analysis of binaries](https://amf3.github.io/articles/virtualization/container_validation/) finds most library dependencies. 
But it's possible that a library can lazy load a dependency at run time. lddtree also fails at finding regular files access at runtime.  Sometimes failed file 
access is expected by the program as it's probing the local environment.

I've created  wrappers around bpftrace to watch for file access when running the new container.  This is useful in knowing whether a container dependency
got missed when defining the manifest. This is something that should be done before publishing the new container image.

While it's possible to inject runc wrappers into Docker, for this task it's simpler to call runc directly, even with Docker installed.  The
project_manifest/tools/build-oci-bundle.py script will extract a Docker image into a OCI bundle for runc and call the bpftrace wrapper.  This also
means that the bpftrace command needs to be available in the validation environment. 

```shell
# Show the help statement
adam@phanpy:~/work/just_enough$ ./project_manifest/tools/build-oci-bundle.py --help
usage: ./project_manifest/tools/build-oci-bundle.py <image:tag> <bundle-dir>

# create the runc bundle from the existing Docker container image
adam@phanpy:~/work/just_enough$ ./project_manifest/tools/build-oci-bundle.py mycontainer:latest ./my_runc_bundle
Building OCI bundle for mycontainer:latest → my_runc_bundle
  attach hook: /home/adam/work/just_enough/project_manifest/tools/attach-ebpf-probe
  detach hook: /home/adam/work/just_enough/project_manifest/tools/detach-ebpf-probe
2e3cc26e54a73116f5a0f22f53873a5031aa0f7e221f8d4a2b957771a671b877
  rootfs extracted to my_runc_bundle/rootfs
  base OCI spec generated at my_runc_bundle/config.json
  capabilities set: ['CAP_SYS_CHROOT', 'CAP_SYS_RESOURCE', 'CAP_SETUID', 'CAP_SETGID', 'CAP_NET_BIND_SERVICE']
  process args: ['/usr/sbin/unbound', '-d', '-c', '/etc/unbound/unbound.conf']
  hooks injected: ['createRuntime', 'poststop']
Bundle ready. Run with: sudo runc run --bundle my_runc_bundle <id>

# Exercise the container image with runc and wrap the container PID with bfptrace.
adam@phanpy:~/work/just_enough$ sudo runc run --bundle my_runc_bundle aaaa
May 23 07:27:14 unbound[1:0] error: cannot open pidfile /var/run/unbound.pid: Permission denied
May 23 07:27:14 unbound[1:0] notice: init module 0: validator
May 23 07:27:14 unbound[1:0] notice: init module 1: iterator
May 23 07:27:14 unbound[1:0] info: start of service (unbound 1.24.2).
...
<cntl-c>
```

The bpftrace wrapper will output log entries to /var/log/ebpf-container-trace.log

```shell
adam@phanpy:~/work/just_enough$ ls -l /var/log/ebpf-container-trace.log 
-rw-r--r-- 1 root root 2390 May 23 07:30 /var/log/ebpf-container-trace.log
```

Use ./project_manifest/tools/generate-report.py To simplify parsing of the trace log,  Output needs some interpretation 
as /lib64 -> /lib is symlinked when creating the staging directory used to build the container image.
Remember to exercise all binaries or they'll show as present but not opened like unbound-anchor.


```shell
adam@phanpy:~/work/just_enough/project_manifest$ ./tools/generate-report.py --manifest ./unbound_dns/container_def.yml 

================================================================
  Container Dependency Report
================================================================
  Container : aaaa...
  Present   : 10 files
  Missing   : 9 files
  Ignored   : 15 files (kernel probes / noise)
================================================================

  FILES PRESENT  (10)
  --------------------------------------------------------------
  OK   /etc/nsswitch.conf  [declared]
  OK   /etc/passwd  [declared]
  OK   /etc/ssl/openssl.cnf  [declared]
  OK   /etc/unbound/unbound.conf  [declared]
  OK   /home/adam/work/just_enough/my_runc_bundle/rootfs  [undeclared — consider adding to manifest]
  OK   /lib64/libc.so.6  [undeclared — consider adding to manifest]
  OK   /lib64/libcrypto.so.3  [undeclared — consider adding to manifest]
  OK   /lib64/libevent-2.1.so.7  [undeclared — consider adding to manifest]
  OK   /lib64/libsodium.so.26  [undeclared — consider adding to manifest]
  OK   /lib64/libssl.so.3  [undeclared — consider adding to manifest]

  FILES MISSING / ENOENT  (9)
  --------------------------------------------------------------
  --   /etc/group
  --   /etc/localtime  [not in manifest]
  --   /lib64/glibc-hwcaps/x86-64-v2/libssl.so.3  [not in manifest]
  --   /lib64/glibc-hwcaps/x86-64-v3/libssl.so.3  [not in manifest]
  --   /lib64/libz.so  [not in manifest]
  --   /usr/lib64/engines-3/gost.so  [not in manifest]
  --   /usr/lib64/glibc-hwcaps/x86-64-v2/libz.so  [not in manifest]
  --   /usr/lib64/glibc-hwcaps/x86-64-v3/libz.so  [not in manifest]
  --   /usr/lib64/libz.so  [not in manifest]

  MANIFEST ENTRIES NEVER OPENED  (9)
  --------------------------------------------------------------
  Declared but not accessed in this run.
  Normal for utility binaries — review before removing.
    ??   /lib
    ??   /lib/libz.so.1
    ??   /usr/bin
    ??   /usr/sbin
    ??   /usr/sbin/unbound
    ??   /usr/sbin/unbound-anchor
    ??   /usr/sbin/unbound-checkconf
    ??   /usr/sbin/unbound-control
    ??   /usr/sbin/unbound-host
```

Update the container image manifest and validate as needed.

### Push the container image 

Once the local image is validated, one can push the image to a local or public container image repository.  This example
uses a local container image repository.

```shell
# Log into the local image repository
adam@phanpy:~/work/just_enough$ docker login --password-stdin --username $GITEA_USER gitea.rb.af9.us < <(echo $GITEA_PASS)
Login Succeeded

# Tag the mycontainer:latest image with the local repo name
adam@phanpy:~/work/just_enough$ docker tag mycontainer:latest gitea.rb.af9.us/${GITEA_USER}/mycontainer:latest 

# push the image
adam@phanpy:~/work/just_enough$ docker push gitea.rb.af9.us/${GITEA_USER}/mycontainer:latest 
The push refers to repository [gitea.rb.af9.us/adam/mycontainer]
f53a8ed06b30: Pushed 
latest: digest: sha256:eebbb2e3b3b9eb18dc26af646f2c212fd9998a4c1452be40430d73354adb9f78 size: 528
```


