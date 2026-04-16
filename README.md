# JustEnough

This project contains Buildroot customizations for creating base container images.

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

## Project Directory Structure

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
