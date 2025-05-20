# JustEnough

This project contains Buildroot customizations for creating base container images.  You can find pre-built JustEnough containers at GitHub's Container Registry.

## Table of Contents

* [About](#about)
* [Pre-built container images](#prebbuilt-container-images)
* [Directory Structure](#directory-structure)
* [Customizing Container Images](#customizing-container-images)
* [Contributing](#contributing)
* [Resources](#resources)

## About

Being able to create and customize a base container image is important.  Doing so let's us define 
which software is inside the container image, which limits the size of the container image.  Another 
benifit is reducing the surface area for security issues.  If the latest CVE targets a common 
command like sudo, and sudo doesn't exist within the container, there's no CVE for that container.

The idea for this project came from a [2015 Sysdig & CoreOS presentation](https://www.youtube.com/watch?v=gMpldbcMHuI) 
by [Brian Redbeard](https://github.com/brianredbeard).

## Prebuilt container images

### Build Status

- [![JustEnough BusyBox](https://github.com/amf3/just_enough/actions/workflows/build_busybox.yml/badge.svg?branch=main)](https://github.com/amf3/just_enough/actions/workflows/build_busybox.yml)
- [![JustEnough OpenJDK21](https://github.com/amf3/just_enough/actions/workflows/build_openjdk21_bash.yml/badge.svg)](https://github.com/amf3/just_enough/actions/workflows/build_openjdk21_bash.yml)
- [![JustEnough OpenJDK21 with Bash](https://github.com/amf3/just_enough/actions/workflows/build_openjdk21.yml/badge.svg)](https://github.com/amf3/just_enough/actions/workflows/build_openjdk21.yml)
- [![JustEnough Python3](https://github.com/amf3/just_enough/actions/workflows/build_python3.yml/badge.svg)](https://github.com/amf3/just_enough/actions/workflows/build_python3.yml)
- [![JustEnough Python3 With Bash](https://github.com/amf3/just_enough/actions/workflows/build_python3_bash.yml/badge.svg)](https://github.com/amf3/just_enough/actions/workflows/build_python3_bash.yml)

### Container Image Tags

Container tags using the buildroot release version followed by the epoch time when the image was built.  Latest will 
always point to the latest built image, regardless of the buildroot release.

### Downloads

Prebuilt container images can be found in the [packages](https://github.com/amf3?tab=packages&repo_name=just_enough) section of this project.  Click on the package name for the container you want to use.  There's a Github Container Registry link at the top of page.  Either "docker pull" or using "FROM ghcr.io/amf3/..." in the Dockerfile will download the image.

The following images are currently offered.

| Image Name | Image documentation | Docker or Podman pull |  Dockerfile |
| ---------- | ------ | --------------------- |  ---------- |
| [just_enough_busybox](https://github.com/users/amf3/packages/container/package/just_enough_busybox) | [BusyBox](https://github.com/amf3/just_enough/blob/main/docs/containers/busybox.md) | docker pull ghcr.io/amf3/just_enough_busybox:latest | FROM ghcr.io/amf3/just_enough_busybox:latest |
| [just_enough_openjdk21](https://github.com/users/amf3/packages/container/package/just_enough_openjdk21) | [OpenJDK21](https://github.com/amf3/just_enough/blob/main/docs/containers/openjdk.md) | docker pull ghcr.io/amf3/just_enough_openjdk21:latest | FROM ghcr.io/amf3/just_enough_openjdk21:latest |
| [just_enough_openjdk21_bash](https://github.com/amf3/just_enough/pkgs/container/just_enough_openjdk21_bash) | [OpenJDK21_Bash](https://github.com/amf3/just_enough/blob/main/docs/containers/openjdk21_bash.md) | docker pull ghcr.io/amf3/just_enough_openjdk21_bash:latest | FROM ghcr.io/amf3/just_enough_openjdk21_bash:latest |
| [just_enough_python3](https://github.com/users/amf3/packages/container/package/just_enough_python3) | [Python3](https://github.com/amf3/just_enough/blob/main/docs/containers/python3.md) | docker pull ghcr.io/amf3/just_enough_python3:latest | FROM ghcr.io/amf3/just_enough_python3:latest |
| [just_enough_python3_bash](https://github.com/users/amf3/packages/container/package/just_enough_python3_bash) | [Python3_Bash](https://github.com/amf3/just_enough/blob/main/docs/containers/python3_bash.md) | docker pull ghcr.io/amf3/just_enough_python3_bash:latest | FROM ghcr.io/amf3/just_enough_python3_bash:latest |

### Container Image Manifest

For now, the Container Image Manifest is published as an artifact.  Click the container name under [Build Status](#build-status) or click on the Actions tab.  Find and click the latest build link and you will see a list of artifacts.  The package_list.txt file will contain what packages and versions were used in building the container.

Better accessibility to the manifest is planned.

## Directory Structure

### board

Contains files needed for buildroot customizations. An example being the user_table.txt for creating users within the container images.

### buildroot

[Buildroot](https://buildroot.org) is the upstrem project which allows for building custom Linux images.  It's included in this repo as a submodule.  

### build_with_docker

Contains a docker-compose and a Makefile for creating a environment to create buildroot containers under Docker.  See the [README](./build_with_docker/README.md) for additional details.

### build_with_multipass

Contains a Makefile for creating a multipass VM to build JustEnough containers.  This is the preferred method of building on macOS.

### configs

JustEnough container specifications

### .github/workflows

Workflow definitions for building & distributing container images

## Customizing Container Images

Prepare the environment

```
$ mkdir $HOME/.buildroot-dl
$ git clone --recursive https://github.com/amf3/just_enough.git
$ cd just_enough
$ export BR2_EXTERNAL=$PWD                # presumes bash is the environment
$ export BR2_DL_DIR=$HOME/.buildroot-dl 
```

List container and load container definition for openjdk11. Entries starting with `container_` are 
part of this project.  (If you would like to customize the busybox container instead of Open JDK, then 
load the busybox_defconfig.)

```
$ make O=$PWD -C ./buildroot list-defconfigs
$ make O=$PWD -C ./buildroot container_busybox_defconfig
```

Customize and save container changes with menuconfig.  Look for the packages menu inside menuconfig for 
adding or removing packages.

```
$ make O=$PWD -C ./buildroot menuconfig
$ make O=$PWD -C ./buildroot savedefconfig
```

Build the container with "all" and list dependencies with "external-deps".

```
$ time make O=$PWD -C ./buildroot source all
$ time make O=$PWD -C ./buildroot external-deps
```

Root file system will be found in the images directory which is turned into a container with "docker import".

## Contributing

1) Fork the Repository
2) Make changes and submit a PR

## Resources
Buildroot [documentation](http://nightly.buildroot.org/manual.html)
