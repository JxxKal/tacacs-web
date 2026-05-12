"""Verify a user's password against an LDAP/AD server by attempting a bind.

This is the live-bind path used by the MAVIS authentication handler — the
sync worker has the service account; this helper checks an end-user's
own password by binding as them.
"""

from __future__ import annotations

from dataclasses import dataclass

from ldap3 import Connection, Server
from ldap3.core.exceptions import LDAPException


class LDAPBindError(RuntimeError):
    """Raised when the LDAP server is unreachable or returns an unexpected error.

    Distinct from "credentials wrong" — `verify_ldap_password` returns False
    for that. This exception means we couldn't make a decision (network down,
    TLS failure, server error).
    """


@dataclass(frozen=True)
class LDAPEndpoint:
    """How to reach a single LDAP/LDAPS server."""

    url: str  # e.g. "ldaps://dc1.corp.tld:636"
    use_tls: bool = True
    receive_timeout: int = 10


def verify_ldap_password(
    endpoint: LDAPEndpoint,
    bind_dn: str,
    password: str,
    *,
    connection_factory: type[Connection] = Connection,
) -> bool:
    """Bind to LDAP as `bind_dn`/`password`. True iff credentials are accepted.

    Returns False on:
    - empty password (some servers anonymous-bind on empty creds, which would
      be a security disaster — explicitly reject without contacting the server)
    - LDAP_INVALID_CREDENTIALS from the server

    Raises `LDAPBindError` on:
    - connection failures (DNS, TCP, TLS)
    - server-side errors not categorised as auth failures
    """
    if not password:
        return False

    server = Server(
        endpoint.url, use_ssl=endpoint.use_tls, connect_timeout=endpoint.receive_timeout
    )
    try:
        with connection_factory(
            server,
            user=bind_dn,
            password=password,
            auto_bind=False,
            read_only=True,
            receive_timeout=endpoint.receive_timeout,
        ) as conn:
            ok = conn.bind()
            if ok:
                return True
            description = (conn.result or {}).get("description", "")
            # 49 = invalidCredentials per RFC 4511.
            if description in {"invalidCredentials", "invalidDNSyntax"}:
                return False
            raise LDAPBindError(f"unexpected bind result: {conn.result}")
    except LDAPException as exc:
        raise LDAPBindError(f"LDAP bind to {endpoint.url} failed: {exc}") from exc
