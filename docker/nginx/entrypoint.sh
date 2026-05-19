#!/bin/sh
# tls-state volume bootstrap.
#
# - Ensures the shared volume directory exists and is writable by both the
#   nginx container (root) and the backend container (uid 1000), so the
#   UI-driven cert upload can land files here.
# - Generates a self-signed bootstrap cert if none is present.

set -eu

TLS_DIR=/etc/nginx/tls
CERT=$TLS_DIR/server.crt
KEY=$TLS_DIR/server.key

mkdir -p "$TLS_DIR"
chgrp 1000 "$TLS_DIR" 2>/dev/null || true
chmod 0775 "$TLS_DIR"

if [ ! -f "$CERT" ] || [ ! -f "$KEY" ]; then
    echo "[tls-bootstrap] no cert at $CERT — generating self-signed (RSA 2048, 825 days)"
    openssl req -x509 -nodes -newkey rsa:2048 \
        -keyout "$KEY" -out "$CERT" \
        -days 825 \
        -subj "/CN=tacacs-web/O=tacacs-web" \
        >/dev/null 2>&1
fi

# Always re-apply perms — covers the case where the backend wrote new
# files into the shared volume as uid 1000.
chgrp 1000 "$CERT" "$KEY" 2>/dev/null || true
chmod 0644 "$CERT"
chmod 0640 "$KEY"
