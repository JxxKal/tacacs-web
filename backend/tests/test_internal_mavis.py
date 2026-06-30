"""Integration smoke for the FastAPI MAVIS auth endpoint.

The handler itself is thin (resolve user → resolve endpoint → evaluate).
These tests verify the FastAPI wiring: dependency injection, request/
response schema, status codes. Policy edge cases are covered by
`test_mavis_authn`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import ldap_bind
from app.db.models import (
    Authorization,
    Device,
    DeviceGroup,
    PrivilegeProfile,
    SystemSetting,
    User,
)
from app.db.session import get_session
from app.main import app


class _FakeScalars:
    def __init__(self, values: list[Any]) -> None:
        self._values = values

    def all(self) -> list[Any]:
        return list(self._values)


class _FakeResult:
    """Stands in for SQLAlchemy `Result` — supports the two access modes we use.

    `scalar_one_or_none()` for the singleton User/SystemSetting case;
    `scalars().all()` for the list-of-rows case (devices, authorizations).
    The fake auto-detects which mode a result is meant for: scalar mode if
    the canned value is anything but a `list`; list mode if it's a `list`.
    """

    def __init__(self, value: Any) -> None:
        self._value = value

    def scalar_one_or_none(self) -> Any:
        return self._value

    def scalars(self) -> _FakeScalars:
        if isinstance(self._value, list):
            return _FakeScalars(self._value)
        return _FakeScalars([self._value] if self._value is not None else [])


class _FakeSession:
    """Yields results in the order the handler issues SELECTs.

    Auth flow issues 2 SELECTs (user, system_setting); info flow issues
    3 (user with groups, devices, authorizations). We hand them back in
    sequence; over-consumption trips `IndexError` so the test signals a
    handler-shape regression loudly.

    Also accepts `add()` and `commit()` no-ops so the M5+ audit-log
    inserts inside the MAVIS handlers don't blow up; the audit content
    itself is exercised by test_api_v1_audit_log against a real session.
    """

    def __init__(self, results: list[Any]) -> None:
        self._results = list(results)
        self.added: list[Any] = []

    async def execute(self, _stmt: Any) -> _FakeResult:
        return _FakeResult(self._results.pop(0))

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def commit(self) -> None:
        return None


def _install_session(results: list[Any]) -> None:
    async def _override() -> AsyncIterator[_FakeSession]:
        yield _FakeSession(results)

    app.dependency_overrides[get_session] = _override


@pytest.fixture(autouse=True)
def _clear_overrides() -> AsyncIterator[None]:
    yield  # type: ignore[misc]
    app.dependency_overrides.clear()


def _patch_verifier(monkeypatch: pytest.MonkeyPatch, fn: Callable[..., bool]) -> None:
    # The handler imports `verify_ldap_password` indirectly via `evaluate`'s
    # default arg, which is bound at function-definition time. So we patch
    # the symbol in `app.auth.mavis_authn` where `evaluate` looks it up.
    monkeypatch.setattr("app.auth.mavis_authn.verify_ldap_password", fn)
    # Also patch the original module so any other call site stays consistent.
    monkeypatch.setattr(ldap_bind, "verify_ldap_password", fn)


def test_unknown_user_returns_nfd() -> None:
    _install_session([None, None])
    with TestClient(app) as client:
        response = client.post("/internal/mavis/auth", json={"username": "ghost", "password": "x"})
    assert response.status_code == 200
    assert response.json() == {"result": "NFD", "reason": "unknown_user"}


def test_endpoint_not_configured_returns_err() -> None:
    user = User(sam_account_name="jan", distinguished_name="cn=jan,dc=x", enabled=True)
    _install_session([user, None])
    with TestClient(app) as client:
        response = client.post("/internal/mavis/auth", json={"username": "jan", "password": "x"})
    assert response.status_code == 200
    assert response.json() == {"result": "ERR", "reason": "ldap_not_configured"}


def test_correct_password_returns_ack(monkeypatch: pytest.MonkeyPatch) -> None:
    user = User(sam_account_name="jan", distinguished_name="cn=jan,dc=x", enabled=True)
    setting = SystemSetting(key="ldap.url", value="ldaps://dc1.corp.example:636")
    _install_session([user, setting])
    _patch_verifier(monkeypatch, lambda *_args, **_kw: True)
    with TestClient(app) as client:
        response = client.post(
            "/internal/mavis/auth", json={"username": "jan", "password": "hunter2"}
        )
    assert response.status_code == 200
    assert response.json() == {"result": "ACK", "reason": None}


def test_wrong_password_returns_nak(monkeypatch: pytest.MonkeyPatch) -> None:
    user = User(sam_account_name="jan", distinguished_name="cn=jan,dc=x", enabled=True)
    setting = SystemSetting(key="ldap.url", value="ldaps://dc1.corp.example:636")
    _install_session([user, setting])
    _patch_verifier(monkeypatch, lambda *_args, **_kw: False)
    with TestClient(app) as client:
        response = client.post("/internal/mavis/auth", json={"username": "jan", "password": "nope"})
    assert response.status_code == 200
    assert response.json() == {"result": "NAK", "reason": "wrong_password"}


def test_empty_username_rejected_by_validation() -> None:
    # The handler should never be called; pydantic rejects the payload first.
    with TestClient(app) as client:
        response = client.post("/internal/mavis/auth", json={"username": "", "password": "x"})
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# /internal/mavis/info
# ---------------------------------------------------------------------------


def _make_user(*, user_id: int = 1, enabled: bool = True) -> User:
    user = User(sam_account_name="jan", distinguished_name="cn=jan,dc=x", enabled=enabled)
    user.id = user_id
    user.groups = []
    return user


def _make_device(*, device_id: int = 1, ip: str = "10.0.0.0/8", dg_id: int = 1) -> Device:
    d = Device(name="d1", ip_or_cidr=ip, device_group_id=dg_id)
    d.id = device_id
    d.device_group = DeviceGroup(name="dg1")
    d.device_group.id = dg_id
    return d


def _make_authorization(*, user_id: int, dg_id: int, priv: int, auth_id: int = 1) -> Authorization:
    p = PrivilegeProfile(
        name="admin",
        tacacs_priv_lvl=priv,
        permit_commands_regex=[],
        deny_commands_regex=[],
        extra_av_pairs={},
    )
    p.id = 1
    a = Authorization(
        principal_user_id=user_id,
        device_group_id=dg_id,
        privilege_profile_id=p.id,
    )
    a.id = auth_id
    a.privilege_profile = p
    return a


def test_info_unknown_user_returns_nfd() -> None:
    _install_session([None])
    with TestClient(app) as client:
        response = client.post(
            "/internal/mavis/info", json={"username": "ghost", "nas_ip": "10.1.1.1"}
        )
    assert response.json() == {"result": "NFD", "reason": "unknown_user", "profile": None}


def test_info_disabled_user_returns_nak() -> None:
    _install_session([_make_user(enabled=False)])
    with TestClient(app) as client:
        response = client.post(
            "/internal/mavis/info", json={"username": "jan", "nas_ip": "10.1.1.1"}
        )
    assert response.json() == {"result": "NAK", "reason": "user_disabled", "profile": None}


def test_info_unknown_nas_returns_nak() -> None:
    user = _make_user(user_id=1)
    _install_session([user, []])  # no devices
    with TestClient(app) as client:
        response = client.post(
            "/internal/mavis/info", json={"username": "jan", "nas_ip": "10.1.1.1"}
        )
    assert response.json() == {"result": "NAK", "reason": "unknown_nas", "profile": None}


def test_info_no_authorization_returns_nak() -> None:
    user = _make_user(user_id=1)
    device = _make_device(device_id=10, ip="10.0.0.0/8", dg_id=1)
    _install_session([user, [device], []])  # no authorizations
    with TestClient(app) as client:
        response = client.post(
            "/internal/mavis/info", json={"username": "jan", "nas_ip": "10.1.1.1"}
        )
    assert response.json() == {"result": "NAK", "reason": "no_authorization", "profile": None}


def test_info_ack_returns_rendered_profile() -> None:
    user = _make_user(user_id=1)
    device = _make_device(device_id=10, ip="10.0.0.0/8", dg_id=1)
    auth = _make_authorization(user_id=1, dg_id=1, priv=15)
    _install_session([user, [device], [auth]])
    with TestClient(app) as client:
        response = client.post(
            "/internal/mavis/info", json={"username": "jan", "nas_ip": "10.1.1.1"}
        )
    body = response.json()
    assert body["result"] == "ACK"
    assert body["reason"] is None
    assert body["profile"] is not None
    assert "set priv-lvl = 15" in body["profile"]
    assert "if (service == shell)" in body["profile"]


# ---------------------------------------------------------------------------
# Case-insensitive username matching (real DB)
#
# AD stores the casing as created (e.g. `SSCHNACK.OT`), but end users type
# their sAMAccountName lowercase. The `_FakeSession` above ignores the SQL
# statement, so the actual `lower(...)` comparison can only be verified
# against a real engine — hence these use the async_db_session fixture.
# ---------------------------------------------------------------------------


async def test_auth_matches_username_case_insensitively(
    async_db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    async_db_session.add(
        User(
            sam_account_name="SSCHNACK.OT",
            distinguished_name="cn=sschnack,dc=x",
            enabled=True,
        )
    )
    async_db_session.add(SystemSetting(key="ldap.url", value="ldaps://dc1.corp.example:636"))
    await async_db_session.commit()

    async def _override() -> AsyncIterator[AsyncSession]:
        yield async_db_session

    app.dependency_overrides[get_session] = _override
    _patch_verifier(monkeypatch, lambda *_args, **_kw: True)
    with TestClient(app) as client:
        response = client.post(
            "/internal/mavis/auth",
            json={"username": "sschnack.ot", "password": "hunter2"},
        )
    assert response.json() == {"result": "ACK", "reason": None}


async def test_info_matches_username_case_insensitively(
    async_db_session: AsyncSession,
) -> None:
    async_db_session.add(
        User(
            sam_account_name="SSCHNACK.OT",
            distinguished_name="cn=sschnack,dc=x",
            enabled=True,
        )
    )
    await async_db_session.commit()

    async def _override() -> AsyncIterator[AsyncSession]:
        yield async_db_session

    app.dependency_overrides[get_session] = _override
    with TestClient(app) as client:
        response = client.post(
            "/internal/mavis/info",
            json={"username": "sschnack.ot", "nas_ip": "10.1.1.1"},
        )
    # No device seeded → resolves past the user lookup to unknown_nas, which
    # proves the user was found case-insensitively (else it'd be unknown_user).
    assert response.json()["reason"] == "unknown_nas"
