"""Closed vocabulary of audit-log action codes (ADR-0009).

Adding a new action requires a code change here. The UI filter chips read
from this module, not from free-form strings — so any action that's
not listed is also not discoverable.
"""

from __future__ import annotations

# Local-admin lifecycle (CLI-only paths)
LOCAL_ADMIN_BOOTSTRAPPED = "local_admin.bootstrapped"
LOCAL_ADMIN_PASSWORD_RESET = "local_admin.password_reset"

# Web-UI auth events
AUTH_LOGIN_SUCCEEDED = "auth.login_succeeded"
AUTH_LOGIN_FAILED = "auth.login_failed"
AUTH_LOGOUT = "auth.logout"
AUTH_SESSION_EXPIRED = "auth.session_expired"

# CRUD events land here when M5b wires audit into the API routes;
# the constants stand ready so handlers don't grow stringly-typed
# `action="device.update"` literals.
DEVICE_CREATED = "device.created"
DEVICE_UPDATED = "device.updated"
DEVICE_DELETED = "device.deleted"
DEVICE_SECRET_ROTATED = "device.secret_rotated"
DEVICE_PREVIOUS_RETIRED = "device.previous_secret_retired"
DEVICE_GROUP_CREATED = "device_group.created"
DEVICE_GROUP_UPDATED = "device_group.updated"
DEVICE_GROUP_DELETED = "device_group.deleted"
PRIVILEGE_PROFILE_CREATED = "privilege_profile.created"
PRIVILEGE_PROFILE_UPDATED = "privilege_profile.updated"
PRIVILEGE_PROFILE_DELETED = "privilege_profile.deleted"
AUTHORIZATION_CREATED = "authorization.created"
AUTHORIZATION_DELETED = "authorization.deleted"

# System-settings changes
SETTING_LDAP_URL_UPDATED = "setting.ldap_url_updated"
SETTING_WEB_BASE_URL_UPDATED = "setting.web_base_url_updated"
TLS_CERT_UPLOADED = "tls.cert_uploaded"
TLS_PFX_UPLOADED = "tls.pfx_uploaded"
TLS_CERT_REGENERATED = "tls.cert_regenerated_self_signed"
SAML_IDP_METADATA_IMPORTED = "saml.idp_metadata_imported"
SAML_MAPPING_UPDATED = "saml.mapping_updated"
SAML_SP_KEYPAIR_REGENERATED = "saml.sp_keypair_regenerated"
LDAP_SYNC_CONFIG_UPDATED = "ldap_sync.config_updated"
LDAP_SYNC_TEST_SUCCEEDED = "ldap_sync.test_succeeded"
LDAP_SYNC_TEST_FAILED = "ldap_sync.test_failed"
LDAP_SYNC_RUN_SUCCEEDED = "ldap_sync.run_succeeded"
LDAP_SYNC_RUN_FAILED = "ldap_sync.run_failed"

# TACACS+ live-auth events from MAVIS. Higher volume than the auth.*
# UI events — one row per NAS login attempt and one per authz
# evaluation. Kept under their own prefix so operators can filter them
# in/out without disrupting the UI/CRUD audit history.
TACACS_AUTHN_SUCCEEDED = "tacacs.authn_succeeded"
TACACS_AUTHN_FAILED = "tacacs.authn_failed"
TACACS_AUTHZ_SUCCEEDED = "tacacs.authz_succeeded"
TACACS_AUTHZ_FAILED = "tacacs.authz_failed"

# Admin maintenance actions
NAS_CONFIG_REGENERATED = "nas_config.regenerated"

# Syslog forwarder lifecycle (M6c)
SYSLOG_CONFIG_UPDATED = "syslog.config_updated"
SYSLOG_TEST_SUCCEEDED = "syslog.test_succeeded"
SYSLOG_TEST_FAILED = "syslog.test_failed"

# First-boot setup wizard (M7)
SETUP_WIZARD_COMPLETED = "setup.wizard_completed"
SETUP_WIZARD_REOPENED = "setup.wizard_reopened"

ALL_ACTIONS = frozenset(
    {
        LOCAL_ADMIN_BOOTSTRAPPED,
        LOCAL_ADMIN_PASSWORD_RESET,
        AUTH_LOGIN_SUCCEEDED,
        AUTH_LOGIN_FAILED,
        AUTH_LOGOUT,
        AUTH_SESSION_EXPIRED,
        DEVICE_CREATED,
        DEVICE_UPDATED,
        DEVICE_DELETED,
        DEVICE_SECRET_ROTATED,
        DEVICE_PREVIOUS_RETIRED,
        DEVICE_GROUP_CREATED,
        DEVICE_GROUP_UPDATED,
        DEVICE_GROUP_DELETED,
        PRIVILEGE_PROFILE_CREATED,
        PRIVILEGE_PROFILE_UPDATED,
        PRIVILEGE_PROFILE_DELETED,
        AUTHORIZATION_CREATED,
        AUTHORIZATION_DELETED,
        SETTING_LDAP_URL_UPDATED,
        SETTING_WEB_BASE_URL_UPDATED,
        TLS_CERT_UPLOADED,
        TLS_PFX_UPLOADED,
        TLS_CERT_REGENERATED,
        SAML_IDP_METADATA_IMPORTED,
        SAML_MAPPING_UPDATED,
        SAML_SP_KEYPAIR_REGENERATED,
        LDAP_SYNC_CONFIG_UPDATED,
        LDAP_SYNC_TEST_SUCCEEDED,
        LDAP_SYNC_TEST_FAILED,
        LDAP_SYNC_RUN_SUCCEEDED,
        LDAP_SYNC_RUN_FAILED,
        TACACS_AUTHN_SUCCEEDED,
        TACACS_AUTHN_FAILED,
        TACACS_AUTHZ_SUCCEEDED,
        TACACS_AUTHZ_FAILED,
        NAS_CONFIG_REGENERATED,
        SYSLOG_CONFIG_UPDATED,
        SYSLOG_TEST_SUCCEEDED,
        SYSLOG_TEST_FAILED,
        SETUP_WIZARD_COMPLETED,
        SETUP_WIZARD_REOPENED,
    }
)
