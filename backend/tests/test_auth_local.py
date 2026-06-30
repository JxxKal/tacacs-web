"""End-to-end tests for /login/local, /logout, /me, and the session dep.

These run against an aiosqlite in-memory DB so the password hash, the
session row, and the audit-log insert all flow through real SQL. The
TestClient handles cookies between requests.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.actions import (
    AUTH_LOGIN_FAILED,
    AUTH_LOGIN_SUCCEEDED,
    AUTH_LOGOUT,
)
from app.auth.password import hash_password
from app.auth.sessions import SESSION_COOKIE_NAME
from app.db.models import AuditLog, LocalAdmin
from app.db.session import get_session
from app.main import app


@pytest.fixture
def client(async_db_session: AsyncSession) -> Iterator[TestClient]:
    async def _override_session() -> AsyncIterator[AsyncSession]:
        yield async_db_session

    app.dependency_overrides[get_session] = _override_session
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.clear()


async def _seed_admin(
    async_db_session: AsyncSession,
    *,
    username: str = "admin",
    password: str = "hunter2-hunter2",
    allowed_cidr: str | None = None,
) -> LocalAdmin:
    row = LocalAdmin(
        id=1,
        username=username,
        password_argon2_hash=hash_password(password),
        allowed_source_cidr=allowed_cidr,
    )
    async_db_session.add(row)
    await async_db_session.commit()
    await async_db_session.refresh(row)
    return row


async def test_login_success_sets_session_cookie_and_audits(
    client: TestClient, async_db_session: AsyncSession
) -> None:
    await _seed_admin(async_db_session)
    r = client.post("/login/local", json={"username": "admin", "password": "hunter2-hunter2"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body == {"username": "admin", "role": "admin", "auth_method": "local"}
    assert SESSION_COOKIE_NAME in client.cookies
    assert client.cookies[SESSION_COOKIE_NAME]

    # /me now reflects the active session.
    r = client.get("/me")
    assert r.status_code == 200
    assert r.json()["username"] == "admin"

    rows = (await async_db_session.execute(select(AuditLog).order_by(AuditLog.id))).scalars().all()
    actions = [r.action for r in rows]
    assert AUTH_LOGIN_SUCCEEDED in actions
    assert AUTH_LOGIN_FAILED not in actions


async def test_login_wrong_password_returns_401_and_audits(
    client: TestClient, async_db_session: AsyncSession
) -> None:
    await _seed_admin(async_db_session)
    r = client.post("/login/local", json={"username": "admin", "password": "wrong"})
    assert r.status_code == 401
    assert SESSION_COOKIE_NAME not in client.cookies

    rows = (
        (
            await async_db_session.execute(
                select(AuditLog).where(AuditLog.action == AUTH_LOGIN_FAILED)
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].summary == "bad_password"


async def test_login_unknown_user_returns_401_with_same_error(
    client: TestClient, async_db_session: AsyncSession
) -> None:
    await _seed_admin(async_db_session)
    r = client.post("/login/local", json={"username": "ghost", "password": "x"})
    assert r.status_code == 401
    # Same detail as the bad-password case — must not leak whether the
    # user exists.
    assert r.json()["detail"] == "invalid_credentials"


async def test_login_cidr_restriction_denies_outside_range(
    client: TestClient, async_db_session: AsyncSession
) -> None:
    # TestClient connects as 127.0.0.1; only allow 10.0.0.0/8 -> deny.
    await _seed_admin(async_db_session, allowed_cidr="10.0.0.0/8")
    r = client.post("/login/local", json={"username": "admin", "password": "hunter2-hunter2"})
    assert r.status_code == 401

    rows = (
        (
            await async_db_session.execute(
                select(AuditLog).where(AuditLog.action == AUTH_LOGIN_FAILED)
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].summary == "cidr_denied"


async def test_logout_revokes_session_and_clears_cookie(
    client: TestClient, async_db_session: AsyncSession
) -> None:
    await _seed_admin(async_db_session)
    client.post("/login/local", json={"username": "admin", "password": "hunter2-hunter2"})
    assert SESSION_COOKIE_NAME in client.cookies

    r = client.post("/logout")
    assert r.status_code == 204
    assert SESSION_COOKIE_NAME not in client.cookies

    # /me without a cookie => 401.
    r = client.get("/me")
    assert r.status_code == 401

    rows = (
        (await async_db_session.execute(select(AuditLog).where(AuditLog.action == AUTH_LOGOUT)))
        .scalars()
        .all()
    )
    assert len(rows) == 1


def test_me_without_session_is_401(client: TestClient) -> None:
    r = client.get("/me")
    assert r.status_code == 401


def test_api_v1_requires_session(client: TestClient) -> None:
    # Unauthenticated CRUD attempt: 401 before any handler logic.
    r = client.post("/api/v1/device-groups", json={"name": "core"})
    assert r.status_code == 401


async def test_api_v1_works_after_login(client: TestClient, async_db_session: AsyncSession) -> None:
    await _seed_admin(async_db_session)
    r = client.post("/login/local", json={"username": "admin", "password": "hunter2-hunter2"})
    assert r.status_code == 200
    r = client.post("/api/v1/device-groups", json={"name": "core"})
    assert r.status_code == 201, r.text
