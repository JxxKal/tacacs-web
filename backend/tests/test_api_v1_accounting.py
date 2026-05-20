"""Tests for the accounting read endpoint."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.sessions import SessionContext, require_session
from app.db.models import AccountingRecord
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
            AccountingRecord(
                ts=base,
                nas_ip="10.0.0.1",
                username="jan",
                port="vty0",
                action="start",
                service="shell",
                task_id="t-001",
                raw_av_pairs={"service": "shell", "task_id": "t-001"},
            ),
            AccountingRecord(
                ts=base + timedelta(minutes=2),
                nas_ip="10.0.0.1",
                username="jan",
                port="vty0",
                action="update",
                cmd="show running-config",
                priv_lvl=15,
                task_id="t-001",
                raw_av_pairs={"cmd": "show running-config", "priv-lvl": "15"},
            ),
            AccountingRecord(
                ts=base + timedelta(minutes=3),
                nas_ip="10.0.0.1",
                username="jan",
                port="vty0",
                action="stop",
                elapsed_seconds=180,
                task_id="t-001",
                raw_av_pairs={"elapsed_time": "180"},
            ),
            AccountingRecord(
                ts=base + timedelta(minutes=5),
                nas_ip="10.0.0.2",
                username="adi",
                action="start",
                task_id="t-002",
                raw_av_pairs={},
            ),
        ]
    )
    await async_db_session.commit()


async def test_lists_newest_first(
    admin_client: TestClient, async_db_session: AsyncSession
) -> None:
    await _seed(async_db_session)
    r = admin_client.get("/api/v1/accounting")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 4
    usernames = [e["username"] for e in body["entries"]]
    assert usernames == ["adi", "jan", "jan", "jan"]


async def test_filter_task_id_correlates_session(
    admin_client: TestClient, async_db_session: AsyncSession
) -> None:
    await _seed(async_db_session)
    r = admin_client.get("/api/v1/accounting?task_id=t-001")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 3
    actions = sorted([e["action"] for e in body["entries"]])
    assert actions == ["start", "stop", "update"]


async def test_filter_cmd_substring(
    admin_client: TestClient, async_db_session: AsyncSession
) -> None:
    await _seed(async_db_session)
    r = admin_client.get("/api/v1/accounting?cmd=running")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["entries"][0]["cmd"] == "show running-config"


async def test_filter_nas_ip(
    admin_client: TestClient, async_db_session: AsyncSession
) -> None:
    await _seed(async_db_session)
    r = admin_client.get("/api/v1/accounting?nas_ip=10.0.0.2")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["entries"][0]["username"] == "adi"


def test_viewer_forbidden(viewer_client: TestClient) -> None:
    r = viewer_client.get("/api/v1/accounting")
    assert r.status_code == 403
