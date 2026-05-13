"""End-to-end tests for the v1 CRUD endpoints against an aiosqlite backend.

Each test mounts the FastAPI app, overrides `get_session` to yield the
shared async test session, and walks one resource through its lifecycle
(create -> get -> update -> conflict -> delete). Cross-resource invariants
(FK enforcement, principal CHECK constraint, dependency RESTRICT on
delete) get their own focused tests.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.sessions import SessionContext, require_session
from app.db.session import get_session
from app.main import app


@pytest.fixture
def client(async_db_session: AsyncSession) -> Iterator[TestClient]:
    async def _override_session() -> AsyncIterator[AsyncSession]:
        yield async_db_session

    async def _override_require_session() -> SessionContext:
        # CRUD tests assume an authenticated admin caller; the auth flow
        # itself is covered separately in test_auth_local.
        return SessionContext(
            token="test-token",
            username="test-admin",
            role="admin",
            auth_method="local",
            actor_id=1,
            client_ip="127.0.0.1",
            user_agent="pytest",
        )

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[require_session] = _override_require_session
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# DeviceGroup
# ---------------------------------------------------------------------------


def test_device_group_lifecycle(client: TestClient) -> None:
    r = client.post("/api/v1/device-groups", json={"name": "core", "description": "core switches"})
    assert r.status_code == 201, r.text
    created = r.json()
    dg_id = created["id"]
    assert created["name"] == "core"

    r = client.get(f"/api/v1/device-groups/{dg_id}")
    assert r.status_code == 200
    assert r.json()["description"] == "core switches"

    r = client.patch(f"/api/v1/device-groups/{dg_id}", json={"description": "updated"})
    assert r.status_code == 200
    assert r.json()["description"] == "updated"

    r = client.get("/api/v1/device-groups")
    assert r.status_code == 200
    assert [g["id"] for g in r.json()] == [dg_id]

    r = client.delete(f"/api/v1/device-groups/{dg_id}")
    assert r.status_code == 204

    r = client.get(f"/api/v1/device-groups/{dg_id}")
    assert r.status_code == 404


def test_device_group_duplicate_name_returns_409(client: TestClient) -> None:
    r = client.post("/api/v1/device-groups", json={"name": "core"})
    assert r.status_code == 201
    r = client.post("/api/v1/device-groups", json={"name": "core"})
    assert r.status_code == 409


# ---------------------------------------------------------------------------
# PrivilegeProfile
# ---------------------------------------------------------------------------


def test_privilege_profile_lifecycle(client: TestClient) -> None:
    r = client.post(
        "/api/v1/privilege-profiles",
        json={
            "name": "ro",
            "tacacs_priv_lvl": 1,
            "permit_commands_regex": ["^show "],
            "deny_commands_regex": [],
            "extra_av_pairs": {"idletime": "30"},
        },
    )
    assert r.status_code == 201, r.text
    pp_id = r.json()["id"]
    assert r.json()["extra_av_pairs"] == {"idletime": "30"}

    r = client.patch(
        f"/api/v1/privilege-profiles/{pp_id}",
        json={"tacacs_priv_lvl": 7, "permit_commands_regex": ["^show ", "^ping "]},
    )
    assert r.status_code == 200
    assert r.json()["tacacs_priv_lvl"] == 7
    assert r.json()["permit_commands_regex"] == ["^show ", "^ping "]

    r = client.delete(f"/api/v1/privilege-profiles/{pp_id}")
    assert r.status_code == 204


def test_privilege_profile_priv_lvl_validation(client: TestClient) -> None:
    r = client.post(
        "/api/v1/privilege-profiles",
        json={"name": "x", "tacacs_priv_lvl": 16},
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Device
# ---------------------------------------------------------------------------


def _make_device_group(client: TestClient, name: str = "core") -> int:
    r = client.post("/api/v1/device-groups", json={"name": name})
    assert r.status_code == 201
    return int(r.json()["id"])


def test_device_lifecycle(client: TestClient) -> None:
    dg_id = _make_device_group(client)
    r = client.post(
        "/api/v1/devices",
        json={
            "name": "core-sw-01",
            "ip_or_cidr": "10.0.0.1",
            "device_group_id": dg_id,
            "current_secret": "shhh",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["has_current_secret"] is True
    assert body["has_previous_secret"] is False
    d_id = body["id"]

    # Plain secrets never appear in any response.
    r = client.get(f"/api/v1/devices/{d_id}")
    assert "shhh" not in r.text

    # Rotation moves the current secret into previous.
    r = client.post(
        f"/api/v1/devices/{d_id}/rotate-secret",
        json={"new_secret": "freshhh"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["has_current_secret"] is True
    assert body["has_previous_secret"] is True

    r = client.post(f"/api/v1/devices/{d_id}/retire-previous")
    assert r.status_code == 200
    body = r.json()
    assert body["has_previous_secret"] is False
    assert body["previous_retired_at"] is not None


def test_device_rejects_unknown_device_group(client: TestClient) -> None:
    r = client.post(
        "/api/v1/devices",
        json={"name": "x", "ip_or_cidr": "10.0.0.1", "device_group_id": 999},
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "unknown_device_group_id"


def test_device_rejects_invalid_ip(client: TestClient) -> None:
    dg_id = _make_device_group(client)
    r = client.post(
        "/api/v1/devices",
        json={"name": "x", "ip_or_cidr": "not-an-ip", "device_group_id": dg_id},
    )
    assert r.status_code == 422


def test_device_group_in_use_cannot_be_deleted(client: TestClient) -> None:
    dg_id = _make_device_group(client)
    r = client.post(
        "/api/v1/devices",
        json={"name": "d1", "ip_or_cidr": "10.0.0.1", "device_group_id": dg_id},
    )
    assert r.status_code == 201
    r = client.delete(f"/api/v1/device-groups/{dg_id}")
    assert r.status_code == 409
    assert r.json()["detail"] == "device_group_in_use"


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------


async def _seed_user(async_db_session: AsyncSession, sam: str = "jan") -> int:
    from app.db.models import User

    user = User(sam_account_name=sam, distinguished_name=f"cn={sam},dc=x", enabled=True)
    async_db_session.add(user)
    await async_db_session.commit()
    await async_db_session.refresh(user)
    return int(user.id)


async def test_authorization_lifecycle(
    client: TestClient, async_db_session: AsyncSession
) -> None:
    user_id = await _seed_user(async_db_session)

    dg_id = _make_device_group(client)
    pp = client.post(
        "/api/v1/privilege-profiles",
        json={"name": "admin", "tacacs_priv_lvl": 15},
    ).json()

    r = client.post(
        "/api/v1/authorizations",
        json={
            "principal_user_id": user_id,
            "device_group_id": dg_id,
            "privilege_profile_id": pp["id"],
        },
    )
    assert r.status_code == 201, r.text
    a_id = r.json()["id"]

    r = client.post(
        "/api/v1/authorizations",
        json={
            "principal_user_id": user_id,
            "device_group_id": dg_id,
            "privilege_profile_id": pp["id"],
        },
    )
    assert r.status_code == 409

    r = client.delete(f"/api/v1/authorizations/{a_id}")
    assert r.status_code == 204


def test_authorization_requires_exactly_one_principal(client: TestClient) -> None:
    dg_id = _make_device_group(client)
    pp = client.post(
        "/api/v1/privilege-profiles",
        json={"name": "admin", "tacacs_priv_lvl": 15},
    ).json()

    r = client.post(
        "/api/v1/authorizations",
        json={
            "device_group_id": dg_id,
            "privilege_profile_id": pp["id"],
        },
    )
    assert r.status_code == 422

    r = client.post(
        "/api/v1/authorizations",
        json={
            "principal_user_id": 1,
            "principal_ad_group_id": 1,
            "device_group_id": dg_id,
            "privilege_profile_id": pp["id"],
        },
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Effective permissions
# ---------------------------------------------------------------------------


async def test_effective_permissions_surfaces_winner_and_overridden(
    client: TestClient, async_db_session: AsyncSession
) -> None:
    from app.db.models import ADGroup, UserADGroup

    user_id = await _seed_user(async_db_session)
    group = ADGroup(sid="S-1-5-21-1", distinguished_name="cn=ops,dc=x", name="ops")
    async_db_session.add(group)
    await async_db_session.commit()
    await async_db_session.refresh(group)
    async_db_session.add(UserADGroup(user_id=user_id, ad_group_id=group.id))
    await async_db_session.commit()

    dg_id = _make_device_group(client)
    admin = client.post(
        "/api/v1/privilege-profiles", json={"name": "admin", "tacacs_priv_lvl": 15}
    ).json()
    ro = client.post(
        "/api/v1/privilege-profiles", json={"name": "ro", "tacacs_priv_lvl": 1}
    ).json()

    # Direct-user grant with priv_lvl 1 overrides the AD-group grant with 15.
    client.post(
        "/api/v1/authorizations",
        json={
            "principal_ad_group_id": group.id,
            "device_group_id": dg_id,
            "privilege_profile_id": admin["id"],
        },
    )
    client.post(
        "/api/v1/authorizations",
        json={
            "principal_user_id": user_id,
            "device_group_id": dg_id,
            "privilege_profile_id": ro["id"],
        },
    )

    r = client.get(f"/api/v1/users/{user_id}/effective-permissions")
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body) == 1
    assert body[0]["device_group_id"] == dg_id
    assert body[0]["winning"]["privilege_profile_id"] == ro["id"]
    assert body[0]["winning"]["tacacs_priv_lvl"] == 1
    assert len(body[0]["overridden"]) == 1
    assert body[0]["overridden"][0]["privilege_profile_id"] == admin["id"]


def test_effective_permissions_unknown_user_404(client: TestClient) -> None:
    r = client.get("/api/v1/users/999/effective-permissions")
    assert r.status_code == 404
