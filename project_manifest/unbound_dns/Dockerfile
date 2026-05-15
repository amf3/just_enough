# Declare the argument with your local folder name as the default value
ARG STAGING_DIR=my_staging_dir
ARG BR_TAG=local_staging

FROM scratch

# Re-declare the ARG after FROM so it's accessible to this build stage
ARG STAGING_DIR
ARG BR_TAG

LABEL org.opencontainers.image.version=${BR_TAG}
LABEL org.opencontainers.image.authors="Adam M. Faris"
LABEL org.opencontainers.image.vendor="amf3"
LABEL org.opencontainers.image.licenses="Apache-2.0"
LABEL org.opencontainers.image.description="Unbound DNS appliance built via Buildroot and the JustEnough project"

# Use the variable in the COPY command
COPY --chown=100:100 ${STAGING_DIR}/ /

EXPOSE 53/tcp
EXPOSE 53/udp

ENTRYPOINT ["/usr/sbin/unbound"]
CMD ["-d", "-c", "/etc/unbound/unbound.conf"]

