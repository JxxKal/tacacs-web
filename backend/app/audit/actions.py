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
    }
)
