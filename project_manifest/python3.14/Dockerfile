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
LABEL org.opencontainers.image.description="A Python3  appliance built via Buildroot and the JustEnough project"

# Use the variable in the COPY command
COPY --chown=65534:65534 ${STAGING_DIR}/ /
USER 65534:65534

CMD ["/usr/bin/python3"]

