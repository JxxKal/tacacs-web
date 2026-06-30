"""Tests for the settings endpoints."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.actions import (
    SETTING_LDAP_URL_UPDATED,
    SETTING_WEB_BASE_URL_UPDATED,
)
from app.auth.sessions import SessionContext, require_session
from app.db.models import AuditLog, SystemSetting
from app.db.session import get_session
from app.main import app


def _make_session(role: str = "admin") -> SessionContext:
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
        return _make_session("admin")

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
        return _make_session("viewer")

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[require_session] = _override_require_session
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.clear()


def test_get_ldap_settings_returns_null_when_unset(admin_client: TestClient) -> None:
    r = admin_client.get("/api/v1/settings/ldap")
    assert r.status_code == 200
    assert r.json() == {"url": None}


async def test_put_ldap_settings_persists_and_audits(
    admin_client: TestClient, async_db_session: AsyncSession
) -> None:
    r = admin_client.put(
        "/api/v1/settings/ldap",
        json={"url": "ldaps://dc01.corp.example:636"},
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"url": "ldaps://dc01.corp.example:636"}

    row = (
        await async_db_session.execute(select(SystemSetting).where(SystemSetting.key == "ldap.url"))
    ).scalar_one()
    assert row.value == "ldaps://dc01.corp.example:636"

    audits = (
        (
            await async_db_session.execute(
                select(AuditLog).where(AuditLog.action == SETTING_LDAP_URL_UPDATED)
            )
        )
        .scalars()
        .all()
    )
    assert len(audits) == 1
    assert audits[0].summary == "ldaps://dc01.corp.example:636"


def test_put_ldap_settings_rejects_bad_scheme(admin_client: TestClient) -> None:
    r = admin_client.put(
        "/api/v1/settings/ldap",
        json={"url": "http://dc01.corp.example"},
    )
    assert r.status_code == 422


def test_viewer_cannot_write_ldap_settings(viewer_client: TestClient) -> None:
    r = viewer_client.put(
        "/api/v1/settings/ldap",
        json={"url": "ldaps://dc01.corp.example:636"},
    )
    assert r.status_code == 403
    assert r.json()["detail"] == "admin_required"


async def test_put_ldap_settings_overwrites_existing_row(
    admin_client: TestClient, async_db_session: AsyncSession
) -> None:
    async_db_session.add(SystemSetting(key="ldap.url", value="ldap://old:389"))
    await async_db_session.commit()
    r = admin_client.put(
        "/api/v1/settings/ldap",
        json={"url": "ldaps://new:636"},
    )
    assert r.status_code == 200
    row = (
        await async_db_session.execute(select(SystemSetting).where(SystemSetting.key == "ldap.url"))
    ).scalar_one()
    assert row.value == "ldaps://new:636"


async def test_put_web_settings_persists_and_audits(
    admin_client: TestClient, async_db_session: AsyncSession
) -> None:
    r = admin_client.put(
        "/api/v1/settings/web",
        json={"base_url": "https://tacacs.corp.example:8443"},
    )
    assert r.status_code == 200
    assert r.json() == {"base_url": "https://tacacs.corp.example:8443"}

    audits = (
        (
            await async_db_session.execute(
                select(AuditLog).where(AuditLog.action == SETTING_WEB_BASE_URL_UPDATED)
            )
        )
        .scalars()
        .all()
    )
    assert len(audits) == 1


def test_put_web_settings_strips_trailing_slash(admin_client: TestClient) -> None:
    r = admin_client.put(
        "/api/v1/settings/web",
        json={"base_url": "https://tacacs.corp.example:8443/"},
    )
    assert r.status_code == 200
    assert r.json()["base_url"] == "https://tacacs.corp.example:8443"


def test_put_web_settings_rejects_non_http(admin_client: TestClient) -> None:
    r = admin_client.put(
        "/api/v1/settings/web",
        json={"base_url": "tacacs.corp.example"},
    )
    assert r.status_code == 422
