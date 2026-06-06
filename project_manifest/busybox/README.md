# The Just_Enough Busybox container image

While this image can run standalone as a normal container image, it's more inteneded to inject
a shell environment inside other distroless containers.

Why would I want a shell as part of a distroless container image?  Normally you wouldn't but its
helpful in debugging situations.  Other use cases are during multi-stage image builds.

The busybox binary is statically compiled to simplify injecting it into existing container images.  There are no
libaries which need to be copied.  The buildroot busybox config is kept at boards/just_enough/busybox_config.

Here's an example Dockerfile showing how a shell can be injected into a shell-less container image.

```text
FROM ghcr.io/amf3/just_enough/busybox:2026.02.2 AS my-busybox # Busybox and Unbound DNS images come from my
FROM ghcr.io/amf3/just_enough/unbound_dns:2026.02.2           # BuildRoot based container build chain. unbound_dns is a minimal/shell-less image.

COPY --from=my-busybox /bin/busybox /bin/busybox              # Inject the busybox binary into the minimal container

SHELL ["/bin/busybox", "sh", "-c"]                            # Distroless containers don't have a shell. Lets reset default shell from /bin/sh to busybox
RUN /bin/busybox --install -s /bin                            # Tell Busybox to self link its applets into the /bin directory

ENTRYPOINT []                                                 # Reset the Entrypoint and CMD statements
CMD ["/bin/ash"]
```


