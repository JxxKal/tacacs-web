"""SP-side keypair generation + IdP-metadata XML parsing.

The SP signs AuthnRequests (optional) and verifies IdP Responses with a
keypair we generate ourselves. The cert is a 10-year self-signed
RSA-2048 certificate; subject CN matches the configured public hostname
so the X.509 is at least nominally identifiable.

IdP-metadata import takes the standard SAML 2.0 metadata XML and extracts
the SSO single-sign-on URL (HTTP-Redirect binding), entity ID, and the
X.509 signing certificate. We persist all three plus the raw XML so the
config can be re-parsed without re-uploading.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from defusedxml import ElementTree as ET

SAML_HTTP_REDIRECT = "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
SAML_HTTP_POST = "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
SAML2_MD_NS = "urn:oasis:names:tc:SAML:2.0:metadata"
XMLDSIG_NS = "http://www.w3.org/2000/09/xmldsig#"


@dataclass(frozen=True)
class IdpMetadata:
    entity_id: str
    sso_url: str
    sso_binding: str
    x509_cert: str  # base64 single-line


class InvalidIdpMetadata(ValueError):
    """Raised when the supplied XML can't be parsed as SAML metadata."""


def generate_sp_keypair(common_name: str) -> tuple[bytes, bytes]:
    """Issue a 10-year self-signed RSA-2048 keypair for SAML signing.

    Returns (cert_pem, key_pem). Both bytes, PEM-encoded.
    """
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=3650))
        .sign(private_key=key, algorithm=hashes.SHA256())
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    key_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return cert_pem, key_pem


def parse_idp_metadata(xml: str) -> IdpMetadata:
    """Pull entity_id, SSO URL, and X.509 cert out of SAML 2.0 metadata XML."""
    try:
        root = ET.fromstring(xml.encode("utf-8") if isinstance(xml, str) else xml)
    except ET.ParseError as exc:
        raise InvalidIdpMetadata(f"not XML: {exc}") from exc

    if not root.tag.endswith("EntityDescriptor"):
        raise InvalidIdpMetadata(f"expected EntityDescriptor at the root, got {root.tag}")
    entity_id = root.attrib.get("entityID")
    if not entity_id:
        raise InvalidIdpMetadata("missing entityID attribute")

    idp_sso = root.find(f"{{{SAML2_MD_NS}}}IDPSSODescriptor")
    if idp_sso is None:
        raise InvalidIdpMetadata("no IDPSSODescriptor in metadata")

    sso = None
    for elem in idp_sso.findall(f"{{{SAML2_MD_NS}}}SingleSignOnService"):
        binding = elem.attrib.get("Binding", "")
        location = elem.attrib.get("Location", "")
        if not location:
            continue
        if binding == SAML_HTTP_REDIRECT:
            sso = (location, binding)
            break
        if sso is None and binding == SAML_HTTP_POST:
            sso = (location, binding)
    if sso is None:
        raise InvalidIdpMetadata("no usable SingleSignOnService (HTTP-Redirect or POST)")

    # Prefer the cert flagged as use="signing"; fall back to the first one if
    # the IdP did not tag any explicitly.
    signing_cert = None
    any_cert = None
    for kd in idp_sso.findall(f"{{{SAML2_MD_NS}}}KeyDescriptor"):
        use = kd.attrib.get("use")
        cert_elem = kd.find(
            f"{{{XMLDSIG_NS}}}KeyInfo/{{{XMLDSIG_NS}}}X509Data/{{{XMLDSIG_NS}}}X509Certificate"
        )
        if cert_elem is None or not cert_elem.text:
            continue
        cleaned = re.sub(r"\s+", "", cert_elem.text)
        if any_cert is None:
            any_cert = cleaned
        if use == "signing":
            signing_cert = cleaned
            break
    cert = signing_cert or any_cert
    if cert is None:
        raise InvalidIdpMetadata("no X.509 signing cert in metadata")

    return IdpMetadata(
        entity_id=entity_id,
        sso_url=sso[0],
        sso_binding=sso[1],
        x509_cert=cert,
    )
