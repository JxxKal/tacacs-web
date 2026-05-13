"""Unit tests for the MAVIS AUTH policy evaluator."""

from __future__ import annotations

import pytest

from app.auth.ldap_bind import LDAPBindError, LDAPEndpoint
from app.auth.mavis_authn import AuthOutcome, evaluate
from app.db.models import User


def _user(*, enabled: bool = True, dn: str = "cn=jan,dc=corp,dc=example") -> User:
    return User(
        sam_account_name="jan",
        distinguished_name=dn,
        enabled=enabled,
    )


@pytest.fixture
def endpoint() -> LDAPEndpoint:
    return LDAPEndpoint(url="ldaps://dc1.corp.example:636")


def test_unknown_user_returns_nfd(endpoint: LDAPEndpoint) -> None:
    outcome = evaluate(None, endpoint, "anything", verifier=lambda *_: True)
    assert outcome == AuthOutcome("NFD", "unknown_user")


def test_disabled_user_returns_nak(endpoint: LDAPEndpoint) -> None:
    outcome = evaluate(_user(enabled=False), endpoint, "hunter2", verifier=lambda *_: True)
    assert outcome == AuthOutcome("NAK", "user_disabled")


def test_no_endpoint_configured_returns_err() -> None:
    outcome = evaluate(_user(), None, "hunter2", verifier=lambda *_: True)
    assert outcome == AuthOutcome("ERR", "ldap_not_configured")


def test_user_without_dn_returns_err(endpoint: LDAPEndpoint) -> None:
    outcome = evaluate(_user(dn=""), endpoint, "hunter2", verifier=lambda *_: True)
    assert outcome == AuthOutcome("ERR", "user_has_no_dn")


def test_ldap_unreachable_returns_err(endpoint: LDAPEndpoint) -> None:
    def boom(*_args: object) -> bool:
        raise LDAPBindError("connection refused")

    outcome = evaluate(_user(), endpoint, "hunter2", verifier=boom)
    assert outcome == AuthOutcome("ERR", "ldap_unreachable")


def test_correct_password_returns_ack(endpoint: LDAPEndpoint) -> None:
    captured: list[tuple[object, ...]] = []

    def verifier(ep: LDAPEndpoint, dn: str, password: str) -> bool:
        captured.append((ep, dn, password))
        return True

    outcome = evaluate(_user(), endpoint, "hunter2", verifier=verifier)
    assert outcome == AuthOutcome("ACK")
    assert captured == [(endpoint, "cn=jan,dc=corp,dc=example", "hunter2")]


def test_wrong_password_returns_nak(endpoint: LDAPEndpoint) -> None:
    outcome = evaluate(_user(), endpoint, "wrong", verifier=lambda *_: False)
    assert outcome == AuthOutcome("NAK", "wrong_password")
