# About
This repo containes Buildroot customizations for creating lightweight containers.  You can find pre-built containers on Docker Hub under 


## Directory Structure

### buildroot

[Buildroot](https://buildroot.org) is the upstrem project which allows for building custom Linux images.  It's included in this repo as a submodule.  Branches are tracked in some dependencies file.

### scripts

Helper Scripts for stuff 


## Getting Started

git clone --recursive 
source scripts/setup
make ...


## Contributing

stuff 

## Resources 

Buildroot [documentation](http://nightly.buildroot.org/manual.html)

## Notes (remove/cleanup later)

### menuconfigs
make menuconfig
make linux-menuconfig
make busybox-menuconfig
make musl-config

### clean up.  
make clean          Run when package is removed from root fs.  
make distclean      Removes everything & all downloads

### defconfig
make savedefconfig      Creates a file named defconfig which needs to be copied & saved as boardname_defconfig
make qemu_x86_defconfig Preloads .config file with qemu specifics
make olddefconfig       Needed to update symbols & dependencies in .config

### Random make stuff
make                    Builds source (Defaults to _all:)
make source             Downloads for local offline builds
make external-deps      List external packages used
make help               A very helpful help statement
make O=mydir            Writes all output files into mydir including .config
make list-defconfigs    Prints community defaults for HW boards like RPI or QEMU

### Examples
make O=$PWD -C ../buildroot qemu_x86_64_defconfig      Change to buildroot

### Important Variables
export BR2_EXTERNAL=$PWD    Path to external tree absolute or relative

### External tree needs 3 files
external.desc
external.mk
Config.in

### TODO
1) need to export BR2_EXTERNAL value
2) Need to call make O=builddir so we don't pollute repo with temp files
3) Capture `make external-deps` into release notes

