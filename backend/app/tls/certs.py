"""X.509 cert + key parsing, validation, and on-disk persistence."""

from __future__ import annotations

import contextlib
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import ExtensionOID, NameOID

# Tunable via the TACACS_WEB_TLS_DIR env var so the test suite can point this
# at a tmpdir without monkey-patching the module.
TLS_DIR = Path(os.environ.get("TACACS_WEB_TLS_DIR", "/var/lib/tacacs-web/tls"))
CERT_FILE = TLS_DIR / "server.crt"
KEY_FILE = TLS_DIR / "server.key"


@dataclass(frozen=True)
class CertInfo:
    subject_cn: str | None
    issuer_cn: str | None
    san_dns: tuple[str, ...]
    not_before: datetime
    not_after: datetime
    fingerprint_sha256: str
    is_self_signed: bool


class CertError(ValueError):
    """Raised on any cert/key validation failure exposed to the UI."""


def parse_cert(pem: bytes) -> CertInfo:
    """Parse a PEM-encoded X.509 cert. Raises `CertError` on malformed input."""
    try:
        cert = x509.load_pem_x509_certificate(pem)
    except ValueError as exc:
        raise CertError(f"could not parse cert: {exc}") from exc

    subject_cn = _first_cn(cert.subject)
    issuer_cn = _first_cn(cert.issuer)
    san = _san_dns_names(cert)
    fp = cert.fingerprint(hashes.SHA256()).hex()
    fp_pretty = ":".join(fp[i : i + 2] for i in range(0, len(fp), 2)).upper()
    return CertInfo(
        subject_cn=subject_cn,
        issuer_cn=issuer_cn,
        san_dns=tuple(san),
        not_before=cert.not_valid_before_utc,
        not_after=cert.not_valid_after_utc,
        fingerprint_sha256=fp_pretty,
        is_self_signed=cert.subject == cert.issuer,
    )


def parse_pkcs12(data: bytes, password: str | None) -> tuple[bytes, bytes]:
    """Extract cert chain + private key from a PKCS#12 / PFX blob.

    Windows AD CS exports the issued cert plus its issuing-CA chain in one
    encrypted .pfx file. We return:
    - PEM chain (leaf first, then any additional certs in upload order) so
      nginx serves the full path that browsers need to walk to the trusted
      root.
    - The private key in PKCS#8 unencrypted PEM (nginx can't unlock a
      password-protected key on its own).

    `password` may be None / empty for unencrypted PFX. Both `None` and an
    empty string are accepted.
    """
    pwd_bytes: bytes | None = None if not password else password.encode("utf-8")
    try:
        bundle = pkcs12.load_pkcs12(data, pwd_bytes)
    except ValueError as exc:
        raise CertError(f"could not parse PFX (wrong password?): {exc}") from exc

    if bundle.cert is None or bundle.cert.certificate is None:
        raise CertError("PFX did not contain an end-entity certificate")
    if bundle.key is None:
        raise CertError("PFX did not contain a private key")

    parts: list[bytes] = [
        bundle.cert.certificate.public_bytes(serialization.Encoding.PEM)
    ]
    for additional in bundle.additional_certs:
        parts.append(additional.certificate.public_bytes(serialization.Encoding.PEM))
    chain_pem = b"".join(parts)

    key_pem = bundle.key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return chain_pem, key_pem


def validate_cert_key_pair(cert_pem: bytes, key_pem: bytes) -> None:
    """Confirm the key matches the cert. Raises `CertError` on mismatch.

    Compares the public key derived from `key_pem` against the one embedded
    in `cert_pem`. Cheap, doesn't reach the network.
    """
    try:
        cert = x509.load_pem_x509_certificate(cert_pem)
    except ValueError as exc:
        raise CertError(f"could not parse cert: {exc}") from exc
    try:
        private_key = serialization.load_pem_private_key(key_pem, password=None)
    except (ValueError, TypeError) as exc:
        raise CertError(f"could not parse private key: {exc}") from exc

    cert_pub = cert.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    key_pub = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    if cert_pub != key_pub:
        raise CertError("private key does not match certificate")


def write_cert_and_key(cert_pem: bytes, key_pem: bytes) -> None:
    """Persist cert + key to the tls-state volume with appropriate perms.

    The nginx container reads from the same volume on its next start, so
    a restart of `nginx` is required for the new cert to take effect.

    Files land group-writable (0664/0660) so the next operator upload can
    overwrite without root help; the nginx-side bootstrap entrypoint
    normalises the same modes on every nginx restart.
    """
    TLS_DIR.mkdir(parents=True, exist_ok=True)
    # If a previous file is read-only for our uid (e.g. the bootstrap cert
    # owned root:root), unlink first so we can recreate. This is the
    # corner case the M5e upload tripped over before the perms got aligned.
    for path in (CERT_FILE, KEY_FILE):
        if path.exists():
            # Fall through on EACCES; write_bytes raises a clearer error.
            with contextlib.suppress(PermissionError):
                path.unlink()
    CERT_FILE.write_bytes(cert_pem)
    KEY_FILE.write_bytes(key_pem)
    CERT_FILE.chmod(0o664)
    KEY_FILE.chmod(0o660)


def generate_self_signed(common_name: str, *, days: int = 825) -> tuple[bytes, bytes]:
    """Issue a fresh self-signed RSA-2048 cert + key pair. Returns PEMs."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, common_name)]
    )
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=days))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName(common_name)]),
            critical=False,
        )
        .sign(private_key=key, algorithm=hashes.SHA256())
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    key_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return cert_pem, key_pem


def _first_cn(name: x509.Name) -> str | None:
    for attr in name.get_attributes_for_oid(NameOID.COMMON_NAME):
        value = attr.value
        if isinstance(value, str):
            return value
    return None


def _san_dns_names(cert: x509.Certificate) -> list[str]:
    try:
        san_ext = cert.extensions.get_extension_for_oid(
            ExtensionOID.SUBJECT_ALTERNATIVE_NAME
        )
    except x509.ExtensionNotFound:
        return []
    san_value = san_ext.value
    if isinstance(san_value, x509.SubjectAlternativeName):
        # `get_values_for_type(DNSName)` already yields the string values.
        return list(san_value.get_values_for_type(x509.DNSName))
    return []
