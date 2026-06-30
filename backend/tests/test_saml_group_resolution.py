"""SAML role resolution from the AD-synced DB (not from a SAML attribute).

FortiAuthenticator authenticates the user but does not reliably carry AD
group memberships in the assertion, so `saml_acs` resolves the role from the
locally-synced `user`/`ad_group` tables keyed by sAMAccountName == NameID.
These tests cover that lookup and its DN matching against the operator's
role mappings.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.saml_routes import _resolve_role, _synced_group_dns
from app.db.models import ADGroup, User

ADMIN_DN = "CN=ResAuth.tier1.AdminGroup,OU=Groups,OU=Tier-1,OU=Global,DC=op-tech,DC=com"
MAPPINGS = ((ADMIN_DN, "admin"),)


async def _seed_user(
    session: AsyncSession,
    *,
    sam: str,
    group_dns: list[str],
    enabled: bool = True,
) -> None:
    groups = [
        ADGroup(sid=f"S-1-5-{i}", distinguished_name=dn, name=None)
        for i, dn in enumerate(group_dns)
    ]
    session.add(
        User(
            sam_account_name=sam,
            distinguished_name=f"CN={sam},DC=op-tech,DC=com",
            enabled=enabled,
            groups=groups,
        )
    )
    await session.commit()


@pytest.mark.asyncio
async def test_synced_groups_resolve_admin_role(async_db_session: AsyncSession) -> None:
    await _seed_user(async_db_session, sam="jakaluza.ra", group_dns=[ADMIN_DN])

    # NameID is matched case-insensitively, mirroring MAVIS authz.
    dns = await _synced_group_dns(async_db_session, "JAKALUZA.RA")
    assert dns == [ADMIN_DN]
    assert _resolve_role(dns, MAPPINGS) == "admin"


@pytest.mark.asyncio
async def test_user_in_no_mapped_group_has_no_role(
    async_db_session: AsyncSession,
) -> None:
    await _seed_user(
        async_db_session,
        sam="someone",
        group_dns=["CN=Other,OU=Groups,DC=op-tech,DC=com"],
    )

    dns = await _synced_group_dns(async_db_session, "someone")
    assert dns == ["CN=Other,OU=Groups,DC=op-tech,DC=com"]
    # Synced, but no mapping matches -> no role (caller emits no_role_mapping).
    assert _resolve_role(dns, MAPPINGS) is None


@pytest.mark.asyncio
async def test_unknown_user_returns_none(async_db_session: AsyncSession) -> None:
    # Distinct from "synced but unmapped": caller emits user_not_synced.
    assert await _synced_group_dns(async_db_session, "ghost") is None


@pytest.mark.asyncio
async def test_disabled_user_returns_none(async_db_session: AsyncSession) -> None:
    await _seed_user(
        async_db_session, sam="gone", group_dns=[ADMIN_DN], enabled=False
    )
    assert await _synced_group_dns(async_db_session, "gone") is None
