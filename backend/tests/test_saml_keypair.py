"""Unit tests for IdP-metadata parsing + SP-keypair generation."""

from __future__ import annotations

import pytest

from app.saml.keypair import (
    InvalidIdpMetadata,
    generate_sp_keypair,
    parse_idp_metadata,
)

VALID_METADATA = """<?xml version="1.0"?>
<md:EntityDescriptor xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
                     entityID="https://idp.example.com/saml">
  <md:IDPSSODescriptor protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <md:KeyDescriptor use="signing">
      <ds:KeyInfo xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
        <ds:X509Data>
          <ds:X509Certificate>
            MIIBszCCARygAwIBAgIJAOJEgEh
            QJqzhMA0GCSqGSIb3DQEBCwUAMA8x
          </ds:X509Certificate>
        </ds:X509Data>
      </ds:KeyInfo>
    </md:KeyDescriptor>
    <md:SingleSignOnService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
                            Location="https://idp.example.com/saml/sso"/>
    <md:SingleSignOnService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
                            Location="https://idp.example.com/saml/sso-post"/>
  </md:IDPSSODescriptor>
</md:EntityDescriptor>
"""


def test_parse_idp_metadata_extracts_fields() -> None:
    md = parse_idp_metadata(VALID_METADATA)
    assert md.entity_id == "https://idp.example.com/saml"
    assert md.sso_url == "https://idp.example.com/saml/sso"
    assert md.sso_binding.endswith("HTTP-Redirect")
    assert md.x509_cert.startswith("MIIB")
    assert "\n" not in md.x509_cert and " " not in md.x509_cert


def test_parse_idp_metadata_rejects_garbage() -> None:
    with pytest.raises(InvalidIdpMetadata):
        parse_idp_metadata("not xml")


def test_parse_idp_metadata_falls_back_to_post_binding() -> None:
    xml = VALID_METADATA.replace("HTTP-Redirect", "Unknown-Binding")
    md = parse_idp_metadata(xml)
    assert md.sso_url.endswith("/sso-post")
    assert md.sso_binding.endswith("HTTP-POST")


def test_parse_idp_metadata_requires_certificate() -> None:
    without_cert = VALID_METADATA.replace("<md:KeyDescriptor", "<md:KeyDescriptor-stripped")
    with pytest.raises(InvalidIdpMetadata):
        parse_idp_metadata(without_cert)


def test_generate_sp_keypair_produces_pem_pair() -> None:
    cert_pem, key_pem = generate_sp_keypair("tacacs.example")
    assert cert_pem.startswith(b"-----BEGIN CERTIFICATE-----")
    assert key_pem.startswith(b"-----BEGIN PRIVATE KEY-----")
    # 10y validity is hardcoded; we don't re-parse here, the cert module's
    # own tests cover that path.
    assert len(cert_pem) > 500
    assert len(key_pem) > 500
