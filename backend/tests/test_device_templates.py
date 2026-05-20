"""Tests for the /api/v1/device-templates hints endpoint."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.sessions import SessionContext, require_session
from app.db.models import SystemSetting
from app.db.session import get_session
from app.main import app


def _ctx(role: str = "admin") -> SessionContext:
    return SessionContext(
        token="t",
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


def test_hints_empty_when_base_url_unset(client: TestClient) -> None:
    r = client.get("/api/v1/device-templates")
    assert r.status_code == 200
    body = r.json()
    assert body["server_host"] is None
    assert body["tacacs_port"] == 49


@pytest.mark.asyncio
async def test_hints_extract_hostname_from_base_url(
    async_db_session: AsyncSession,
) -> None:
    async_db_session.add(
        SystemSetting(key="web.base_url", value="https://tacacs.corp.example:8444/")
    )
    await async_db_session.commit()

    async def _override_session() -> AsyncIterator[AsyncSession]:
        yield async_db_session

    async def _override_require_session() -> SessionContext:
        return _ctx("admin")

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[require_session] = _override_require_session
    try:
        with TestClient(app) as c:
            r = c.get("/api/v1/device-templates")
            assert r.status_code == 200
            assert r.json() == {
                "server_host": "tacacs.corp.example",
                "tacacs_port": 49,
            }
    finally:
        app.dependency_overrides.clear()
