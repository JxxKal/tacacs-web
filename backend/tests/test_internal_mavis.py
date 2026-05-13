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

from app.auth import ldap_bind
from app.db.models import SystemSetting, User
from app.db.session import get_session
from app.main import app


class _FakeResult:
    def __init__(self, value: Any) -> None:
        self._value = value

    def scalar_one_or_none(self) -> Any:
        return self._value


class _FakeSession:
    """Yields results in the order the handler issues SELECTs.

    The internal_mavis handler issues exactly two SELECTs per request:
    first the User, then the SystemSetting for `ldap.url`. We hand back
    results in that order; if the handler ever asks for more, the test
    will trip on `IndexError` which is exactly the signal we want.
    """

    def __init__(self, results: list[Any]) -> None:
        self._results = list(results)

    async def execute(self, _stmt: Any) -> _FakeResult:
        return _FakeResult(self._results.pop(0))


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
        response = client.post(
            "/internal/mavis/auth", json={"username": "ghost", "password": "x"}
        )
    assert response.status_code == 200
    assert response.json() == {"result": "NFD", "reason": "unknown_user"}


def test_endpoint_not_configured_returns_err() -> None:
    user = User(sam_account_name="jan", distinguished_name="cn=jan,dc=x", enabled=True)
    _install_session([user, None])
    with TestClient(app) as client:
        response = client.post(
            "/internal/mavis/auth", json={"username": "jan", "password": "x"}
        )
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
        response = client.post(
            "/internal/mavis/auth", json={"username": "jan", "password": "nope"}
        )
    assert response.status_code == 200
    assert response.json() == {"result": "NAK", "reason": "wrong_password"}


def test_empty_username_rejected_by_validation() -> None:
    # The handler should never be called; pydantic rejects the payload first.
    with TestClient(app) as client:
        response = client.post(
            "/internal/mavis/auth", json={"username": "", "password": "x"}
        )
    assert response.status_code == 422
