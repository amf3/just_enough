# Declare the argument with your local folder name as the default value
ARG STAGING_DIR=my_staging_dir

FROM scratch

# Re-declare the ARG after FROM so it's accessible to this build stage
ARG STAGING_DIR

# Use the variable in the COPY command
COPY --chown=100:100 ${STAGING_DIR}/ /

EXPOSE 53/tcp
EXPOSE 53/udp

ENTRYPOINT ["/usr/sbin/unbound"]
CMD ["-d", "-c", "/etc/unbound/unbound.conf"]

