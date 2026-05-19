"""SAML 2.0 Service Provider integration (ADR-0003 day-job half).

SP-init only (no SLO, no IdP-initiated). All persistent config lives in
`system_setting` / `system_secret`; the python3-saml Auth helper is
constructed per request from those values via `build_auth_for_request`.
"""

from app.saml.config import (
    SAML_GROUP_ATTR_DEFAULT,
    SamlConfig,
    SamlNotConfigured,
    build_auth_for_request,
    load_saml_config,
    sp_acs_url,
    sp_entity_id,
    sp_metadata_xml,
)
from app.saml.keypair import (
    generate_sp_keypair,
    parse_idp_metadata,
)

__all__ = [
    "SAML_GROUP_ATTR_DEFAULT",
    "SamlConfig",
    "SamlNotConfigured",
    "build_auth_for_request",
    "generate_sp_keypair",
    "load_saml_config",
    "parse_idp_metadata",
    "sp_acs_url",
    "sp_entity_id",
    "sp_metadata_xml",
]
