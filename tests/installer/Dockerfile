FROM debian:12-slim
ENV container=docker
RUN printf '#!/bin/sh\nexit 101\n' > /usr/sbin/policy-rc.d \
    && chmod 755 /usr/sbin/policy-rc.d \
    && apt-get update -qq \
    && for package_attempt in 1 2 3; do \
         DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
           systemd systemd-sysv dbus python3 python3-venv ca-certificates curl wget procps iproute2 && break; \
         [ "$package_attempt" -lt 3 ] || exit 1; \
       done \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*
STOPSIGNAL SIGRTMIN+3
CMD ["/sbin/init"]
