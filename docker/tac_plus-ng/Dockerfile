# tac_plus-ng built from source (Marc Huber's event-driven-servers).
# Upstream: https://github.com/MarcJHuber/event-driven-servers
# License:  BSD-style (see upstream tac_plus-ng/COPYING)
#
# The build is pinned to a specific upstream commit since the project
# publishes no git tags. Bump EDS_REF to roll forward.

ARG EDS_REF=6221675ac4758d3c450dc047cdaec4068aefae96

FROM debian:bookworm-slim AS build
ARG EDS_REF
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        curl \
        libc-ares-dev \
        libpcre2-dev \
        libssl-dev \
        perl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
RUN curl -fsSL "https://github.com/MarcJHuber/event-driven-servers/archive/${EDS_REF}.tar.gz" \
        | tar -xzf - --strip-components=1 \
    && ./configure tac_plus-ng spawnd \
    && make -j"$(nproc)" \
    && make install

FROM debian:bookworm-slim
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        gettext-base \
        libc-ares2 \
        libpcre2-8-0 \
        libssl3 \
        netcat-openbsd \
        python3 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -g 1000 tacacs \
    && useradd -u 1000 -g 1000 -d /var/lib/tac_plus-ng -m -s /usr/sbin/nologin tacacs \
    && mkdir -p /var/log/tac_plus-ng /etc/tac_plus-ng /opt/tacacs-web \
    && chown 1000:1000 /var/log/tac_plus-ng /etc/tac_plus-ng /opt/tacacs-web

COPY --from=build /usr/local/sbin/spawnd /usr/local/sbin/spawnd
COPY --from=build /usr/local/sbin/tac_plus-ng /usr/local/sbin/tac_plus-ng

COPY docker/tac_plus-ng/tac_plus-ng.cfg.template /etc/tac_plus-ng/tac_plus-ng.cfg.template
COPY docker/tac_plus-ng/entrypoint.sh /usr/local/bin/entrypoint
COPY docker/tac_plus-ng/mavis_child.py /opt/tacacs-web/mavis_child.py

RUN chmod 0755 /usr/local/bin/entrypoint /opt/tacacs-web/mavis_child.py

USER 1000:1000
EXPOSE 49/tcp
ENTRYPOINT ["/usr/local/bin/entrypoint"]
