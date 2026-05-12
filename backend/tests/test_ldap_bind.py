"""Tests for `verify_ldap_password` using ldap3's in-memory mock strategy."""

from __future__ import annotations

import pytest
from ldap3 import MOCK_SYNC, Connection, Server
from ldap3.core.exceptions import LDAPSocketOpenError

from app.auth.ldap_bind import LDAPBindError, LDAPEndpoint, verify_ldap_password


@pytest.fixture
def fake_server() -> Server:
    return Server("fake", get_info=None)


@pytest.fixture
def endpoint() -> LDAPEndpoint:
    return LDAPEndpoint(url="ldaps://fake:636", use_tls=False, receive_timeout=2)


def _make_mock_factory(server: Server):
    """Return a Connection subclass that uses MOCK_SYNC against `server`."""

    class MockConnection(Connection):
        def __init__(self, *args: object, **kwargs: object) -> None:
            kwargs["client_strategy"] = MOCK_SYNC
            super().__init__(server, *args[1:], **kwargs)

        def __enter__(self) -> Connection:
            return self

        def __exit__(self, *exc_info: object) -> None:
            self.unbind()

    return MockConnection


def test_correct_password_accepted(fake_server: Server, endpoint: LDAPEndpoint) -> None:
    dn = "cn=jan,ou=People,dc=corp,dc=example"
    factory = _make_mock_factory(fake_server)
    bootstrap = factory(fake_server)
    bootstrap.strategy.add_entry(dn, {"objectClass": ["inetOrgPerson"], "userPassword": "hunter2"})
    bootstrap.unbind()

    assert verify_ldap_password(endpoint, dn, "hunter2", connection_factory=factory) is True


def test_wrong_password_rejected(fake_server: Server, endpoint: LDAPEndpoint) -> None:
    dn = "cn=jan,ou=People,dc=corp,dc=example"
    factory = _make_mock_factory(fake_server)
    bootstrap = factory(fake_server)
    bootstrap.strategy.add_entry(dn, {"objectClass": ["inetOrgPerson"], "userPassword": "hunter2"})
    bootstrap.unbind()

    assert verify_ldap_password(endpoint, dn, "wrong-password", connection_factory=factory) is False


def test_empty_password_short_circuits(fake_server: Server, endpoint: LDAPEndpoint) -> None:
    """Anonymous bind disguised as a "successful" auth must never happen."""
    factory = _make_mock_factory(fake_server)
    assert verify_ldap_password(endpoint, "cn=any,dc=x", "", connection_factory=factory) is False


def test_connection_failure_raises(endpoint: LDAPEndpoint) -> None:
    # Use the real Connection class against a TCP port nothing is listening on.
    endpoint = LDAPEndpoint(
        url="ldap://127.0.0.1:1",  # IANA "reserved", never listens
        use_tls=False,
        receive_timeout=1,
    )
    with pytest.raises((LDAPBindError, LDAPSocketOpenError)):
        verify_ldap_password(endpoint, "cn=any,dc=x", "anything")
