"""Unit tests for the M7 setup-wizard status endpoint."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.sessions import SessionContext, require_session
from app.db.models import (
    DeviceGroup,
    LocalAdmin,
    PrivilegeProfile,
    SystemSetting,
)
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
def client(async_db_session: AsyncSession) -> Iterator[TestClient]:
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


def test_empty_db_reports_no_steps_done(client: TestClient) -> None:
    r = client.get("/api/v1/setup")
    assert r.status_code == 200
    body = r.json()
    assert body["completed"] is False
    assert body["can_complete"] is False
    keys = {s["key"] for s in body["steps"]}
    assert {
        "local_admin",
        "web_base_url",
        "tls",
        "ldap_url",
        "first_device_group",
        "first_privilege_profile",
    } <= keys
    by_key = {s["key"]: s for s in body["steps"]}
    assert by_key["local_admin"]["done"] is False
    assert by_key["local_admin"]["required"] is True
    assert by_key["ldap_sync"]["required"] is False


@pytest.mark.asyncio
async def test_can_complete_when_required_steps_done(
    async_db_session: AsyncSession, tmp_path: object
) -> None:
    from app.tls.certs import CERT_FILE

    async_db_session.add_all(
        [
            LocalAdmin(
                username="root",
                password_argon2_hash="$argon2id$dummy",
            ),
            DeviceGroup(name="default", description="default group"),
            PrivilegeProfile(
                name="priv15",
                tacacs_priv_lvl=15,
                permit_commands_regex=[],
                deny_commands_regex=[],
                extra_av_pairs={},
            ),
            SystemSetting(key="web.base_url", value="https://tacacs.example/"),
            SystemSetting(key="ldap.url", value="ldaps://dc01.corp.example:636"),
        ]
    )
    await async_db_session.commit()

    CERT_FILE.parent.mkdir(parents=True, exist_ok=True)
    CERT_FILE.write_bytes(b"-----BEGIN CERTIFICATE-----\nfake\n-----END CERTIFICATE-----\n")

    async def _override_session() -> AsyncIterator[AsyncSession]:
        yield async_db_session

    async def _override_require_session() -> SessionContext:
        return _ctx("admin")

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[require_session] = _override_require_session
    try:
        with TestClient(app) as c:
            r = c.get("/api/v1/setup")
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["can_complete"] is True
            assert body["completed"] is False

            done = c.post("/api/v1/setup/complete")
            assert done.status_code == 200, done.text
            assert done.json()["completed"] is True

            reopen = c.post("/api/v1/setup/reopen")
            assert reopen.status_code == 200
            assert reopen.json()["completed"] is False
    finally:
        app.dependency_overrides.clear()
        if CERT_FILE.exists():
            CERT_FILE.unlink()


def test_complete_refuses_when_required_missing(client: TestClient) -> None:
    r = client.post("/api/v1/setup/complete")
    assert r.status_code == 400
    assert r.json()["detail"] == "required_steps_incomplete"


def test_completion_requires_admin(async_db_session: AsyncSession) -> None:
    async def _override_session() -> AsyncIterator[AsyncSession]:
        yield async_db_session

    async def _override_require_session() -> SessionContext:
        return _ctx("viewer")

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[require_session] = _override_require_session
    try:
        with TestClient(app) as c:
            r = c.post("/api/v1/setup/complete")
            assert r.status_code == 403
    finally:
        app.dependency_overrides.clear()
