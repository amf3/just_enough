FROM scratch

COPY --chown=0:0 my_fake_root/ /

EXPOSE 53/tcp
EXPOSE 53/udp

ENTRYPOINT ["/usr/sbin/unbound", "-d", "-c", "/etc/unbound/unbound.conf"]
