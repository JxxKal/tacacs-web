"""Compose the python3-saml settings + helper for per-request SP construction.

`load_saml_config` reads the persisted SP keypair + IdP metadata-derived
fields from `system_setting` / `system_secret` and packages them as a
typed dataclass. `build_auth_for_request` produces a `OneLogin_Saml2_Auth`
ready to handle one /saml/login or /saml/acs HTTP request.

The web base URL is read from `system_setting('web.base_url')` if set,
falling back to `settings.base_url` (env). All SP URLs are derived from
this so the IdP-side metadata (`/saml/metadata`) stays consistent.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from onelogin.saml2.auth import OneLogin_Saml2_Auth
from onelogin.saml2.settings import OneLogin_Saml2_Settings
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import SystemSecret, SystemSetting

SAML_GROUP_ATTR_DEFAULT = "memberOf"
"""Attribute name in the IdP Response carrying AD group claims."""

SETTING_IDP_ENTITY_ID = "saml.idp_entity_id"
SETTING_IDP_SSO_URL = "saml.idp_sso_url"
SETTING_IDP_SSO_BINDING = "saml.idp_sso_binding"
SETTING_IDP_X509_CERT = "saml.idp_x509_cert"
SETTING_IDP_METADATA_XML = "saml.idp_metadata_xml"
SETTING_GROUP_ATTRIBUTE = "saml.group_attribute"
SETTING_ROLE_MAPPINGS = "saml.role_mappings"  # JSON: [{ad_group, role}, ...]
SECRET_SP_PRIVATE_KEY = "saml.sp_private_key_pem"
SECRET_SP_CERT = "saml.sp_certificate_pem"
SETTING_WEB_BASE_URL = "web.base_url"


class SamlNotConfigured(RuntimeError):
    """Raised when /saml/* is hit but SAML hasn't been wired yet."""


@dataclass(frozen=True)
class SamlConfig:
    base_url: str
    idp_entity_id: str
    idp_sso_url: str
    idp_sso_binding: str
    idp_x509_cert: str
    sp_certificate_pem: str
    sp_private_key_pem: str
    group_attribute: str
    role_mappings: tuple[tuple[str, str], ...]
    """Tuple of (ad_group_dn_or_name, role) — order is operator-controlled."""


async def _read_setting(session: AsyncSession, key: str) -> str | None:
    row = (
        await session.execute(select(SystemSetting).where(SystemSetting.key == key))
    ).scalar_one_or_none()
    return row.value if row is not None else None


async def _read_secret(session: AsyncSession, key: str) -> str | None:
    row = (
        await session.execute(select(SystemSecret).where(SystemSecret.key == key))
    ).scalar_one_or_none()
    return row.value if row is not None else None


async def load_saml_config(session: AsyncSession) -> SamlConfig:
    """Load + validate the persisted SAML config. Raises SamlNotConfigured."""
    base_url = await _read_setting(session, SETTING_WEB_BASE_URL) or settings.base_url
    if not base_url:
        raise SamlNotConfigured("web.base_url is not set")

    idp_entity_id = await _read_setting(session, SETTING_IDP_ENTITY_ID)
    idp_sso_url = await _read_setting(session, SETTING_IDP_SSO_URL)
    idp_sso_binding = await _read_setting(session, SETTING_IDP_SSO_BINDING) or ""
    idp_cert = await _read_setting(session, SETTING_IDP_X509_CERT)
    if not (idp_entity_id and idp_sso_url and idp_cert):
        raise SamlNotConfigured("IdP metadata has not been imported yet")

    sp_cert = await _read_secret(session, SECRET_SP_CERT)
    sp_key = await _read_secret(session, SECRET_SP_PRIVATE_KEY)
    if not (sp_cert and sp_key):
        raise SamlNotConfigured("SP keypair has not been generated yet")

    group_attr = (
        await _read_setting(session, SETTING_GROUP_ATTRIBUTE) or SAML_GROUP_ATTR_DEFAULT
    )
    raw_mappings = await _read_setting(session, SETTING_ROLE_MAPPINGS) or "[]"
    try:
        decoded = json.loads(raw_mappings)
    except json.JSONDecodeError:
        decoded = []
    mappings = tuple(
        (entry["ad_group"], entry["role"])
        for entry in decoded
        if isinstance(entry, dict) and "ad_group" in entry and "role" in entry
    )

    return SamlConfig(
        base_url=base_url.rstrip("/"),
        idp_entity_id=idp_entity_id,
        idp_sso_url=idp_sso_url,
        idp_sso_binding=idp_sso_binding,
        idp_x509_cert=idp_cert,
        sp_certificate_pem=sp_cert,
        sp_private_key_pem=sp_key,
        group_attribute=group_attr,
        role_mappings=mappings,
    )


def sp_entity_id(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/saml/metadata"


def sp_acs_url(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/saml/acs"


def _strip_pem_armor(pem: str) -> str:
    """python3-saml wants the cert / key with the BEGIN/END lines stripped."""
    lines = [
        line.strip()
        for line in pem.splitlines()
        if line.strip() and not line.startswith("-----")
    ]
    return "".join(lines)


def to_onelogin_settings(cfg: SamlConfig) -> dict[str, Any]:
    """Render the python3-saml settings dict from our typed config."""
    return {
        "strict": True,
        "debug": False,
        "sp": {
            "entityId": sp_entity_id(cfg.base_url),
            "assertionConsumerService": {
                "url": sp_acs_url(cfg.base_url),
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST",
            },
            "NameIDFormat": "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress",
            "x509cert": _strip_pem_armor(cfg.sp_certificate_pem),
            "privateKey": _strip_pem_armor(cfg.sp_private_key_pem),
        },
        "idp": {
            "entityId": cfg.idp_entity_id,
            "singleSignOnService": {
                "url": cfg.idp_sso_url,
                "binding": cfg.idp_sso_binding
                or "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
            },
            "x509cert": cfg.idp_x509_cert,
        },
        "security": {
            "authnRequestsSigned": True,
            "wantAssertionsSigned": True,
            "wantMessagesSigned": False,
            "signatureAlgorithm": "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256",
            "digestAlgorithm": "http://www.w3.org/2001/04/xmlenc#sha256",
        },
    }


def build_request_data(
    *,
    http_host: str,
    server_port: int,
    https: bool,
    request_uri: str,
    get_data: dict[str, str] | None = None,
    post_data: dict[str, str] | None = None,
) -> dict[str, Any]:
    return {
        "https": "on" if https else "off",
        "http_host": http_host,
        "server_port": str(server_port),
        "script_name": request_uri,
        "get_data": dict(get_data or {}),
        "post_data": dict(post_data or {}),
    }


def build_auth_for_request(
    cfg: SamlConfig,
    *,
    request_data: dict[str, Any],
) -> OneLogin_Saml2_Auth:
    """Wrap python3-saml's Auth constructor with our merged config."""
    saml_settings = OneLogin_Saml2_Settings(
        to_onelogin_settings(cfg),
        custom_base_path=None,
        sp_validation_only=False,
    )
    return OneLogin_Saml2_Auth(request_data, old_settings=saml_settings)


def sp_metadata_xml(cfg: SamlConfig) -> str:
    """Render the SP-side metadata XML for upload into the IdP."""
    saml_settings = OneLogin_Saml2_Settings(
        to_onelogin_settings(cfg),
        sp_validation_only=True,
    )
    metadata = saml_settings.get_sp_metadata()
    errors = saml_settings.validate_metadata(metadata)
    if errors:
        raise RuntimeError(f"could not render SP metadata: {errors}")
    return metadata if isinstance(metadata, str) else metadata.decode("utf-8")


def _normalise_host_port(base_url: str) -> tuple[str, int, bool]:
    parsed = urlparse(base_url)
    host = parsed.hostname or "localhost"
    https = parsed.scheme == "https"
    port = parsed.port or (443 if https else 80)
    return host, port, https
