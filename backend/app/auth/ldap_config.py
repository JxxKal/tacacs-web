"""Load the live-LDAPS endpoint config from the DB.

The `LDAPEndpoint` used by `verify_ldap_password` is reconstructed from a
single `system_setting` row (`ldap.url`). TLS is implied by the URL scheme:
`ldaps://` → use_tls=True, anything else → False. Single-domain v1 only,
per ADR-0002 — multi-endpoint resolution is out of scope.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.ldap_bind import LDAPEndpoint
from app.db.models import SystemSetting

SETTING_LDAP_URL = "ldap.url"
DEFAULT_RECEIVE_TIMEOUT = 10


async def resolve_ldap_endpoint(session: AsyncSession) -> LDAPEndpoint | None:
    """Return the configured live-bind endpoint, or None if not set up yet."""
    row = (
        await session.execute(select(SystemSetting).where(SystemSetting.key == SETTING_LDAP_URL))
    ).scalar_one_or_none()
    if row is None or not row.value:
        return None
    url = row.value.strip()
    return LDAPEndpoint(
        url=url,
        use_tls=url.lower().startswith("ldaps://"),
        receive_timeout=DEFAULT_RECEIVE_TIMEOUT,
    )
