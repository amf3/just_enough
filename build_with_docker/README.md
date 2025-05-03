# Build With Docker

## About

This is an effort to build a just_enough container within Docker.  To use
it one needs to have both make and Docker installed.  

Then run `make shell` to create and enter the build environment.  Both BR2_EXTERNAL
and BR2_DL_DIR are defined in the docker-compose file so those don't need to be
redefined unless there's a need to change the values.

To clean up the build environment, exit the contianer and run `make clean_all`.  This
will delete the container and any named volumes, but leave the image alone.

See the Makefile for further details.

## Suggestion

This doesn't work well with Docker Desktop 4.40.0 on MacOS. The build process 
causes Docker engine to crash. :(   It's advised to instead use the 
build_with_multipass content if building on MacOS.

The docker build environement does work well with Linux and is recommended if
building under a Linux OS.  

