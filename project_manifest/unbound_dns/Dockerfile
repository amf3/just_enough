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
LABEL org.opencontainers.image.description="Unbound DNS appliance built via Buildroot and the JustEnough project"


COPY --chown=101:101 ${STAGING_DIR}/ /
COPY --chown=101:101 --from=bb_shell /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-certificates.crt

RUN --mount=type=bind,from=bb_shell,source=/usr/bin/ash,target=/usr/bin/ash \
    --mount=type=bind,from=bb_shell,source=/usr/bin/busybox,target=/usr/bin/busybox \
    ["/usr/bin/ash", "-c", "/usr/bin/unbound-anchor -a /etc/unbound/get-dnssec-root.key || true"]

#RUN --mount=type=bind,from=bb_shell,source=/usr/bin/ash,target=/usr/bin/ash \
#    --mount=type=bind,from=bb_shell,source=/usr/bin/busybox,target=/usr/bin/busybox \
#    --mount=type=bind,from=bb_shell,source=/usr/bin/wget,target=/usr/bin/wget \
#    ["/usr/bin/ash", "-c", "/usr/bin/wget -O /etc/unbound/root.hints http://www.internic.net/domain/named.cache"]

RUN --mount=type=bind,from=bb_shell,source=/usr/bin/busybox,target=/usr/bin/busybox \
    ["/usr/bin/busybox", "wget", "-O", "/etc/unbound/root.hints", "http://www.internic.net/domain/named.cache"]

RUN --mount=type=bind,from=bb_shell,source=/usr/bin/busybox,target=/usr/bin/busybox \
    ["/usr/bin/busybox", "chown", "101:101", "/etc/unbound/root.hints"]

RUN --mount=type=bind,from=bb_shell,source=/usr/bin/busybox,target=/usr/bin/busybox \
    ["/usr/bin/busybox", "chown", "101:101", "/etc/unbound/get-dnssec-root.key"]

EXPOSE 53/tcp
EXPOSE 53/udp

ENTRYPOINT ["/usr/sbin/unbound"]
CMD ["-d", "-c", "/etc/unbound/unbound.conf"]
