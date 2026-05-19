"""Tests for the audit-log read endpoint."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.actions import (
    AUTH_LOGIN_FAILED,
    AUTH_LOGIN_SUCCEEDED,
    TACACS_AUTHN_FAILED,
    TACACS_AUTHN_SUCCEEDED,
)
from app.auth.sessions import SessionContext, require_session
from app.db.models import AuditLog
from app.db.session import get_session
from app.main import app


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


async def _seed(async_db_session: AsyncSession) -> None:
    base = datetime.now(UTC) - timedelta(hours=1)
    async_db_session.add_all(
        [
            AuditLog(
                ts=base,
                actor_username_snapshot="alice",
                actor_role="admin",
                auth_method="local",
                action=AUTH_LOGIN_SUCCEEDED,
            ),
            AuditLog(
                ts=base + timedelta(minutes=5),
                actor_username_snapshot="bob",
                actor_role="unknown",
                auth_method="local",
                action=AUTH_LOGIN_FAILED,
                summary="bad_password",
                client_ip="10.0.0.1",
            ),
            AuditLog(
                ts=base + timedelta(minutes=10),
                actor_username_snapshot="jakaluza.ra",
                actor_role="tacacs_user",
                auth_method="tacacs",
                action=TACACS_AUTHN_SUCCEEDED,
                client_ip="10.180.56.130",
            ),
            AuditLog(
                ts=base + timedelta(minutes=15),
                actor_username_snapshot="jakaluza.ra",
                actor_role="tacacs_user",
                auth_method="tacacs",
                action=TACACS_AUTHN_FAILED,
                summary="wrong_password",
                client_ip="10.180.56.130",
            ),
        ]
    )
    await async_db_session.commit()


async def test_lists_newest_first_with_total(
    admin_client: TestClient, async_db_session: AsyncSession
) -> None:
    await _seed(async_db_session)
    r = admin_client.get("/api/v1/audit-log")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 4
    assert body["limit"] == 100
    assert body["offset"] == 0
    actions = [e["action"] for e in body["entries"]]
    assert actions == [
        TACACS_AUTHN_FAILED,
        TACACS_AUTHN_SUCCEEDED,
        AUTH_LOGIN_FAILED,
        AUTH_LOGIN_SUCCEEDED,
    ]


async def test_filter_by_action(
    admin_client: TestClient, async_db_session: AsyncSession
) -> None:
    await _seed(async_db_session)
    r = admin_client.get(
        f"/api/v1/audit-log?action={TACACS_AUTHN_FAILED}"
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["entries"][0]["summary"] == "wrong_password"


async def test_filter_by_auth_method_and_username(
    admin_client: TestClient, async_db_session: AsyncSession
) -> None:
    await _seed(async_db_session)
    r = admin_client.get("/api/v1/audit-log?auth_method=tacacs&username=jakaluza")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    for e in body["entries"]:
        assert e["auth_method"] == "tacacs"
        assert "jakaluza" in e["actor_username_snapshot"]


async def test_pagination(
    admin_client: TestClient, async_db_session: AsyncSession
) -> None:
    await _seed(async_db_session)
    r = admin_client.get("/api/v1/audit-log?limit=2&offset=2")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 4
    assert body["limit"] == 2
    assert body["offset"] == 2
    assert len(body["entries"]) == 2


def test_viewer_forbidden(viewer_client: TestClient) -> None:
    r = viewer_client.get("/api/v1/audit-log")
    assert r.status_code == 403


def test_known_actions_includes_tacacs_codes(admin_client: TestClient) -> None:
    r = admin_client.get("/api/v1/audit-log/actions")
    assert r.status_code == 200
    actions = r.json()["actions"]
    assert TACACS_AUTHN_SUCCEEDED in actions
    assert TACACS_AUTHN_FAILED in actions
    assert AUTH_LOGIN_SUCCEEDED in actions
