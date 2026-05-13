"""Policy decision for a MAVIS AUTH request.

Pure-Python evaluator: given the DB-resolved `User`, the configured
`LDAPEndpoint`, and a candidate password, decide ACK/NAK/NFD/ERR. The
synchronous `verifier` argument is injected so unit tests can pass a stub
without touching ldap3. The FastAPI handler wraps the verifier call in
`asyncio.to_thread` because `verify_ldap_password` performs blocking I/O.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from app.auth.ldap_bind import LDAPBindError, LDAPEndpoint, verify_ldap_password
from app.db.models import User

AuthResult = Literal["ACK", "NAK", "NFD", "ERR"]

Verifier = Callable[[LDAPEndpoint, str, str], bool]


@dataclass(frozen=True)
class AuthOutcome:
    result: AuthResult
    reason: str | None = None


def evaluate(
    user: User | None,
    endpoint: LDAPEndpoint | None,
    password: str,
    *,
    verifier: Verifier | None = None,
) -> AuthOutcome:
    """Decide the MAVIS verdict for one (user, password) attempt.

    Fail-closed semantics (ADR-0002): any uncertainty about whether the
    password is valid (no LDAP endpoint configured, AD unreachable, missing
    bind DN) yields ERR rather than NAK or ACK, so the daemon can hand the
    request over to local break-glass accounts.
    """
    if verifier is None:
        # Resolve at call time so tests can monkeypatch the symbol on this module.
        verifier = verify_ldap_password
    if user is None:
        return AuthOutcome("NFD", "unknown_user")
    if not user.enabled:
        return AuthOutcome("NAK", "user_disabled")
    if endpoint is None:
        return AuthOutcome("ERR", "ldap_not_configured")
    if not user.distinguished_name:
        return AuthOutcome("ERR", "user_has_no_dn")
    try:
        ok = verifier(endpoint, user.distinguished_name, password)
    except LDAPBindError:
        return AuthOutcome("ERR", "ldap_unreachable")
    if ok:
        return AuthOutcome("ACK")
    return AuthOutcome("NAK", "wrong_password")
