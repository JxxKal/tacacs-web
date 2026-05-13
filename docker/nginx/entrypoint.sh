#!/bin/sh
# Generate a self-signed bootstrap cert into /etc/nginx/tls/ if no cert
# is already present. M7 replaces this with a UI-driven upload flow on top
# of the same volume.

set -eu

TLS_DIR=/etc/nginx/tls
CERT=$TLS_DIR/server.crt
KEY=$TLS_DIR/server.key

mkdir -p "$TLS_DIR"

if [ ! -f "$CERT" ] || [ ! -f "$KEY" ]; then
    echo "[tls-bootstrap] no cert at $CERT — generating self-signed (RSA 2048, 825 days)"
    openssl req -x509 -nodes -newkey rsa:2048 \
        -keyout "$KEY" -out "$CERT" \
        -days 825 \
        -subj "/CN=tacacs-web/O=tacacs-web" \
        >/dev/null 2>&1
    chmod 0600 "$KEY"
fi
