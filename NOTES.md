
## Getting Started

TODO: "git clone --recursive" or "git submodule update --remote"
TODO: source scripts/setup
TODO: make ...
TODO: ABI considerations with glibc.  Want old kernel selection for glibc apps.  Might be able to fake older glibc via busybox config
https://sourceware.org/git/?p=glibc.git;a=blob;f=sysdeps/unix/sysv/linux/dl-osinfo.h;h=fe46a2c9de16f7cca0196766051d0d0e375a4096;hb=HEAD#l44

git clone --recursive 
cd just_enough
export BR2_EXTERNAL=$PWD
make O=$PWD ./buildroot list-defconfigs
make O=$PWD ./buildroot container_base_defconfig
time make O=$PWD ./buildroot all


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

### Important Variables
export BR2_EXTERNAL=$PWD                                  Path to external tree absolute or relative path
export BR2_DEFCONFIG=$PWD/configs/<boardname>_defconfig   Where defconfig file is saved. Recommend to point at configs dir

### Examples
make O=$PWD -C ./buildroot qemu_x86_64_defconfig      Change to buildroot for source, output files in $PWD

### External tree needs 3 files
external.desc
external.mk
Config.in

### TODO
1) Add Behavior Policy under contributions
2) need to export BR2_EXTERNAL value
3) ~~Need to call make O=builddir so we don't pollute repo with temp files~~ Done
4) Capture `make external-deps` into release notes
5) Tag containers with BuildRoot Relase/Version & allow for tag revisions
    a) Need to allow for more then 1 container build per day.
    b) Use 'latest' tag to point at shiney new.
    c) how can I push these to dockerhub ?


