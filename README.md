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

## Prebuilt container images

### Build Status

- [![JustEnough BusyBox](https://github.com/opsmekanix/just_enough/actions/workflows/build_busybox.yml/badge.svg?branch=main)](https://github.com/opsmekanix/just_enough/actions/workflows/build_busybox.yml)
- [![JustEnough OpenJDK11](https://github.com/opsmekanix/just_enough/actions/workflows/build_openjdk11_bash.yml/badge.svg)](https://github.com/opsmekanix/just_enough/actions/workflows/build_openjdk11_bash.yml)
- [![JustEnough Bash With OpenJDK11](https://github.com/opsmekanix/just_enough/actions/workflows/build_openjdk11.yml/badge.svg)](https://github.com/opsmekanix/just_enough/actions/workflows/build_openjdk11.yml)
- [![JustEnough Python3](https://github.com/opsmekanix/just_enough/actions/workflows/build_python3.yml/badge.svg)](https://github.com/opsmekanix/just_enough/actions/workflows/build_python3.yml)
- [![JustEnough Python3 With Bash](https://github.com/opsmekanix/just_enough/actions/workflows/build_python3_bash.yml/badge.svg)](https://github.com/opsmekanix/just_enough/actions/workflows/build_python3_bash.yml)


### Downloads

Prebuilt container images can be found in the [packages](https://github.com/opsmekanix?tab=packages&repo_name=just_enough) section of this project.  Click on the package name for the container you want to use.  There's a Github Container Registry link at the top of page.  Either "docker pull" or using "FROM ghcr.io/opsmekanix/..." in the Dockerfile will download the image.

### Container Image Tags

Currently container tags are based on the build date in year-month-day format.  There is no "latest" tag.  Future plans will change the tag name from using the build date to using the buildroot release tag.  This will provide a means of mapping a container to release of buildroot.

### Container Image Manifest

For now, the Container Image Manifest is published as an artifact.  Click the container name under [Build Status](#build-status) or click on the Actions tab.  Find and click the latest build link and you will see a list of artifacts.  The package_list.txt file will contain what packages and versions were used in building the container.

Better accessibility to the manifest is planned.

## Directory Structure

### buildroot

[Buildroot](https://buildroot.org) is the upstrem project which allows for building custom Linux images.  It's included in this repo as a submodule.  

### configs

JustEnough container specifications

### scripts

Helper Scripts for customizing containers.

### .github/workflows

Workflow definitions for building & distributing container images

## Customizing Container Images

Prepare the environment

```
git clone --recursive 
cd just_enough
export BR2_EXTERNAL=$PWD
```

List container and load container definition

```
make O=$PWD -C ./buildroot list-defconfigs
make O=$PWD -C ./buildroot container_openjdk11_defconfig
```

Customize and save container changes.  Look for the packages menu inside menuconfig for 
adding or removing packages.

```
make O=$PWD -C ./buildroot menuconfig
make O=$PWD -C ./buildroot savedefconfig
```

Build the container with "all" and list contents with "external-deps".

```
time make O=$PWD -C ./buildroot all
time make O=$PWD -C ./buildroot external-deps
```

Root file system will be found in the images directory which is turned into a container with "docker import".


## Contributing

1) Fork the Repository
2) Make changes and submit a PR

## Resources
Buildroot [documentation](http://nightly.buildroot.org/manual.html)
