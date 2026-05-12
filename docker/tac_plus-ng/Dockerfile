# tac_plus-ng built from source. Pinned upstream tag set at build time via ARG.
#
# Upstream:  https://www.pro-bono-publico.de/projects/tac_plus-ng.html
# License:   See upstream NOTICE; bundled in /opt/tac_plus-ng/NOTICE in the final image.
#
# This Dockerfile is a stub for M1; M2 fills in the real build + entrypoint.

FROM debian:bookworm-slim AS build

ARG TAC_PLUS_NG_VERSION=DEVEL.202601
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        curl \
        libssl-dev \
        libldap2-dev \
        libpcre2-dev \
        zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# TODO(M2): fetch + verify + ./configure + make + make install for ${TAC_PLUS_NG_VERSION}
# Build artifact path: /opt/tac_plus-ng

FROM debian:bookworm-slim
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        libpcre2-8-0 \
        libldap-2.5-0 \
        netcat-openbsd \
        python3 \
        python3-pip \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -g 1000 tacacs \
    && useradd -u 1000 -g 1000 -d /var/lib/tac_plus-ng -m -s /usr/sbin/nologin tacacs

# COPY --from=build /opt/tac_plus-ng /opt/tac_plus-ng
# COPY docker/tac_plus-ng/entrypoint.sh /usr/local/bin/entrypoint
# COPY docker/tac_plus-ng/tac_plus-ng.cfg.template /etc/tac_plus-ng/tac_plus-ng.cfg.template
# COPY backend/app/mavis /opt/mavis

USER 1000:1000
EXPOSE 49/tcp
# ENTRYPOINT ["/usr/local/bin/entrypoint"]
CMD ["sleep", "infinity"]  # M1 placeholder
