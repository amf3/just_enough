# Declare the argument with your local folder name as the default value
ARG STAGING_DIR=my_staging_dir
ARG BR_TAG=local_staging

FROM ghcr.io/amf3/just_enough/busybox:latest AS bb_shell

FROM scratch

# Re-declare the ARG after FROM so it's accessible to this build stage
ARG STAGING_DIR
ARG BR_TAG

LABEL org.opencontainers.image.version=${BR_TAG}
LABEL org.opencontainers.image.authors="Adam M. Faris"
LABEL org.opencontainers.image.vendor="amf3"
LABEL org.opencontainers.image.licenses="Apache-2.0"
LABEL org.opencontainers.image.description="A Samba4 appliance built via Buildroot and the JustEnough project"

COPY ${STAGING_DIR}/ /

RUN --mount=type=bind,from=bb_shell,source=/usr/bin/busybox,target=/usr/bin/busybox \
 ["/usr/bin/busybox", "chmod", "0700", "/var/lib/samba/private", "/var/log/samba/cores"]

RUN --mount=type=bind,from=bb_shell,source=/usr/bin/busybox,target=/usr/bin/busybox \
 ["/usr/bin/busybox", "chmod", "0755", "/var/log/samba", "/var/run/samba", "/var/cache/samba", "/var/lock/samba"]

CMD ["/usr/bin/smbd", "--foreground", "--no-process-group", "--debug-stdout"]