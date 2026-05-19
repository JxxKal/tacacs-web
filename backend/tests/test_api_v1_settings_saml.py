"""Tests for /api/v1/settings/saml — read, IdP import, mapping, keypair."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.actions import (
    SAML_IDP_METADATA_IMPORTED,
    SAML_MAPPING_UPDATED,
    SAML_SP_KEYPAIR_REGENERATED,
)
from app.auth.sessions import SessionContext, require_session
from app.db.models import AuditLog, SystemSecret, SystemSetting
from app.db.session import get_session
from app.main import app
from tests.test_saml_keypair import VALID_METADATA


def _ctx(role: str = "admin") -> SessionContext:
    return SessionContext(
        token="test-token",
        username=f"test-{role}",
        role=role,
        auth_method="local",
        actor_id=1,
        client_ip="127.0.0.1",
        user_agent="pytest",
    )


@pytest.fixture
def admin_client(async_db_session: AsyncSession) -> Iterator[TestClient]:
    async def _override_session() -> AsyncIterator[AsyncSession]:
        yield async_db_session

    async def _override_require_session() -> SessionContext:
        return _ctx("admin")

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[require_session] = _override_require_session
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def viewer_client(async_db_session: AsyncSession) -> Iterator[TestClient]:
    async def _override_session() -> AsyncIterator[AsyncSession]:
        yield async_db_session

    async def _override_require_session() -> SessionContext:
        return _ctx("viewer")

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[require_session] = _override_require_session
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.clear()


def test_initial_status_is_unconfigured(admin_client: TestClient) -> None:
    r = admin_client.get("/api/v1/settings/saml")
    assert r.status_code == 200
    body = r.json()
    assert body["configured"] is False
    assert body["sp_has_keypair"] is False
    assert body["idp_entity_id"] is None
    assert body["group_attribute"] == "memberOf"
    assert body["role_mappings"] == []


async def test_import_idp_metadata_persists_and_audits(
    admin_client: TestClient, async_db_session: AsyncSession
) -> None:
    r = admin_client.put(
        "/api/v1/settings/saml/idp-metadata",
        json={"xml": VALID_METADATA},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["idp_entity_id"] == "https://idp.example.com/saml"
    assert body["idp_sso_url"].endswith("/sso")
    assert body["idp_cert_present"] is True

    stored = (
        await async_db_session.execute(
            select(SystemSetting).where(SystemSetting.key == "saml.idp_entity_id")
        )
    ).scalar_one()
    assert stored.value == "https://idp.example.com/saml"

    audits = (
        await async_db_session.execute(
            select(AuditLog).where(AuditLog.action == SAML_IDP_METADATA_IMPORTED)
        )
    ).scalars().all()
    assert len(audits) == 1


def test_import_idp_metadata_rejects_garbage(admin_client: TestClient) -> None:
    r = admin_client.put(
        "/api/v1/settings/saml/idp-metadata",
        json={"xml": "<not-metadata/>"},
    )
    assert r.status_code == 400


def test_viewer_cannot_import_idp(viewer_client: TestClient) -> None:
    r = viewer_client.put(
        "/api/v1/settings/saml/idp-metadata",
        json={"xml": VALID_METADATA},
    )
    assert r.status_code == 403


async def test_update_mapping_persists(
    admin_client: TestClient, async_db_session: AsyncSession
) -> None:
    r = admin_client.put(
        "/api/v1/settings/saml/mapping",
        json={
            "group_attribute": "http://schemas/.../role",
            "role_mappings": [
                {"ad_group": "CN=net-admins,OU=Groups,DC=corp,DC=example", "role": "admin"},
                {"ad_group": "CN=net-ops,OU=Groups,DC=corp,DC=example", "role": "operator"},
            ],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["group_attribute"] == "http://schemas/.../role"
    assert len(body["role_mappings"]) == 2

    audits = (
        await async_db_session.execute(
            select(AuditLog).where(AuditLog.action == SAML_MAPPING_UPDATED)
        )
    ).scalars().all()
    assert len(audits) == 1


def test_update_mapping_rejects_unknown_role(admin_client: TestClient) -> None:
    r = admin_client.put(
        "/api/v1/settings/saml/mapping",
        json={
            "group_attribute": "memberOf",
            "role_mappings": [{"ad_group": "foo", "role": "superuser"}],
        },
    )
    assert r.status_code == 422


async def test_regenerate_keypair_persists_and_audits(
    admin_client: TestClient, async_db_session: AsyncSession
) -> None:
    r = admin_client.post(
        "/api/v1/settings/saml/sp-keypair",
        json={"common_name": "tacacs.example"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["sp_has_keypair"] is True
    assert body["sp_acs_url"] is not None and body["sp_acs_url"].endswith("/saml/acs")
    assert body["sp_entity_id"] is not None and body["sp_entity_id"].endswith("/saml/metadata")

    key_row = (
        await async_db_session.execute(
            select(SystemSecret).where(SystemSecret.key == "saml.sp_private_key_pem")
        )
    ).scalar_one()
    assert "BEGIN PRIVATE KEY" in key_row.value

    audits = (
        await async_db_session.execute(
            select(AuditLog).where(AuditLog.action == SAML_SP_KEYPAIR_REGENERATED)
        )
    ).scalars().all()
    assert len(audits) == 1


def test_viewer_cannot_regenerate_keypair(viewer_client: TestClient) -> None:
    r = viewer_client.post(
        "/api/v1/settings/saml/sp-keypair",
        json={"common_name": "x"},
    )
    assert r.status_code == 403
