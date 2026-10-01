ARG STAGING_DIR=my_samba
ARG BR_TAG=local_staging

# Ephemeral tooling stage
FROM ghcr.io/amf3/just_enough/busybox:latest AS bb_shell

# Production runtime stage
FROM scratch

ARG STAGING_DIR
ARG BR_TAG

LABEL org.opencontainers.image.version=${BR_TAG}
LABEL org.opencontainers.image.authors="Adam M. Faris"
LABEL org.opencontainers.image.vendor="amf3"
LABEL org.opencontainers.image.licenses="Apache-2.0"
LABEL org.opencontainers.image.description="A minimal Samba4 appliance built via Buildroot and JustEnough"

# Copy Buildroot rootfs
COPY ${STAGING_DIR}/ /

# Copy default/baseline samba config
COPY ./project_manifest/samba4/smb.conf /etc/samba/smb.conf

# Fix runtime directory permissions
RUN --mount=type=bind,from=bb_shell,source=/usr/bin/busybox,target=/usr/bin/busybox \
    ["/usr/bin/busybox", "chmod", "0700", "/var/lib/samba/private"]

RUN --mount=type=bind,from=bb_shell,source=/usr/bin/busybox,target=/usr/bin/busybox \
    ["/usr/bin/busybox", "chmod", "0755", "/var/log/samba", "/var/run/samba", "/var/cache/samba"]

# Tell subsequent RUN commands to use /bin/busybox as shell. Make sure one mounts busybox into the container when calling RUN
SHELL ["/usr/bin/busybox", "sh", "-c"]

# Populate /etc/passwd and primary /etc/group from samba_secrets
RUN --mount=type=bind,from=bb_shell,source=/usr/bin/busybox,target=/usr/bin/busybox \
    --mount=type=secret,id=samba_secrets,target=/run/secrets/samba_secrets \
    /usr/bin/busybox awk -F ':' '!/^#/ && NF { \
      print $2 ":x:" $1 ":" $1 ":" $2 ":/dev/null:/bin/false" >> "/etc/passwd"; \
      print $2 ":x:" $1 ":" >> "/etc/group" \
    }' /run/secrets/samba_secrets

# Populate shared groups in /etc/group from samba_groups (if file is supplied)
RUN --mount=type=bind,from=bb_shell,source=/usr/bin/busybox,target=/usr/bin/busybox \
    --mount=type=secret,id=samba_groups,target=/run/secrets/samba_groups,required=false \
    /usr/bin/busybox awk -F ':' '!/^#/ && NF { \
      print $1 ":x:" $2 ":" $3 >> "/etc/group" \
    }' /run/secrets/samba_groups 2>/dev/null || true

# Populate Samba User DB
RUN --mount=type=bind,from=bb_shell,source=/usr/bin/busybox,target=/usr/bin/busybox \
    --mount=type=secret,id=samba_secrets,target=/run/secrets/samba_secrets \
    /usr/bin/busybox awk -F ':' \
    '!/^#/ && NF { print "(echo \"" $3 "\"; echo \"" $3 "\") | /usr/bin/smbpasswd -a -s " $2 }' \
    /run/secrets/samba_secrets | /usr/bin/busybox sh

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD ["/usr/bin/smbclient", "-L", "//127.0.0.1", "-N", "-U", "healthcheck%AMIOK", "-c", "exit"]

CMD ["/usr/bin/smbd", "--foreground", "--no-process-group", "--debug-stdout"]