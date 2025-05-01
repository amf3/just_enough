# Building under Multipass

## Requirements

This directory will allow us to build just_enough containers under Multipass.
Please have **multipass and make installed as prerequisites**.

## How to use this build environment?

This build environment creates just_enough containers under Multipass on my M2 Macbook Air.  This is needed as
the build process for just_enough containers requires a Linux build environment.  CD to the build_with_multipass
directory and run the following to get started:

* To create the build environement, run `make create`.  
* When this is done, run `make shell` to get a shell environement. 
     * On first boot, you will see a message stating the VM needs a reboot. Run `sudo reboot` and `make shell` again
* In another terminal that's associated with the Host/MacOS environment, CD to the build_with_mutipass directory and run `make copy_to`
     * This will copy the just_enough repo to the VM allowing for just_enough containers to be built.
* Flip back to the terminal associated with the VM and follow the just_enough [README.md](https://github.com/amf3/just_enough/blob/main/README.md) directions for creating containers
     * The VM is runnning as an arm64 VM on MacOS.  As containers built in the VM are x86 based, root filesystems need to be copied back to the Host/MacOS environment to run under Rosetta. This is done with `make get_rootfs`.
* To copy the buildroot config back to the Host/MacOS environment, run `make copy_from`.
    * Running `git status` should show the new buildroot configs are present.
    
Remember that this project is using Multipass to create the build environment inside a VM.  Any Multipass command will
work for managing the VM.  The Makefile is being provided as a convience.  

## Makefile targets

* **create**     : This will create and launch the VM with dependencies installed.
* **start**      : This will start the VM.  If the VM hasn't been created, it will likely fail.
* **stop**       : This will stop the VM.  If the VM hasn't been created, it will likely fail.
* **shell**      : This will open a shell to the VM buid environment.
* **clean**      : Clean will delete the VM.
* **copy_to**    : This will copy the just_enough repo to the VM.
* **copy_from**  : This will copy changes made to buildroot configs to the host OS.
* **get_rootfs** : Copies the rootfs.tar.gz artifact from the VM to the Host/MacOS environment.