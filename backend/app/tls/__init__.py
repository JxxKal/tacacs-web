"""TLS cert parsing + on-disk management.

The cert + key sit on the `tls-state` Docker volume, mounted at
`/var/lib/tacacs-web/tls` in the backend and `/etc/nginx/tls` in the nginx
container. nginx reads them on (re)start; we don't reach into the daemon
to reload, so an explicit container restart is needed after upload.

Files are written with group 1000 (the backend's `app` user / shared with
the nginx-side bootstrap script) so both containers can read; the key is
0640 to keep it readable only by the group.
"""

from app.tls.certs import (
    CertInfo,
    generate_self_signed,
    parse_cert,
    validate_cert_key_pair,
    write_cert_and_key,
)

__all__ = [
    "CertInfo",
    "generate_self_signed",
    "parse_cert",
    "validate_cert_key_pair",
    "write_cert_and_key",
]
