# BusyBox Container Image
## About
The BusyBox Container image is a small image less then 3MB and uses MUSL for the C Library.  Use cases
are adhoc shells for inspecting running containers. It could also be used as a base image in a multistage build.

## Examples

Build & deploy a busybox container

This is our Dockerfile
```
FROM just_enough_busybox
ENTRYPOINT ["/bin/ash"]
```

Build the container and start an ash shell.
```
$ docker build -t hello-busybox .
$ docker run -it hello-busybox
```

