"""Server-side web sessions: create, look up, slide, revoke.

ADR-0003 ground rules: HttpOnly + Secure + SameSite=Lax cookie; 8h sliding
expiration capped by a 24h hard expiry. Tokens are 256 bits of OS entropy,
base64url-encoded — long enough that DB collision attacks are not on the
table.

`require_session` is the FastAPI dependency that the HTTP routes inject.
It reads the cookie, looks up the session, slides expiry if still valid,
and yields a `SessionContext` describing the logged-in caller.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import Cookie, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import WebSession
from app.db.session import get_session

SESSION_COOKIE_NAME = "tacacs_web_session"
SESSION_SLIDING_LIFETIME = timedelta(hours=8)
SESSION_HARD_LIFETIME = timedelta(hours=24)


@dataclass(frozen=True)
class SessionContext:
    """The caller's identity for one HTTP request."""

    token: str
    username: str
    role: str
    auth_method: Literal["local", "saml"]
    actor_id: int | None
    client_ip: str | None
    user_agent: str | None


def _new_token() -> str:
    # 256 bits, urlsafe base64. Length 43.
    return secrets.token_urlsafe(32)


async def create_session(
    session: AsyncSession,
    *,
    username: str,
    role: str,
    auth_method: Literal["local", "saml"],
    actor_id: int | None,
    client_ip: str | None = None,
) -> WebSession:
    now = datetime.now(UTC)
    row = WebSession(
        token=_new_token(),
        auth_method=auth_method,
        local_admin_id=actor_id if auth_method == "local" else None,
        username_snapshot=username,
        role=role,
        created_at=now,
        last_seen_at=now,
        expires_at=now + SESSION_SLIDING_LIFETIME,
        hard_expires_at=now + SESSION_HARD_LIFETIME,
        client_ip=client_ip,
    )
    session.add(row)
    return row


async def revoke_session(session: AsyncSession, token: str) -> bool:
    row = await session.get(WebSession, token)
    if row is None:
        return False
    await session.delete(row)
    return True


def _as_utc(value: datetime) -> datetime:
    """Coerce a possibly tz-naive datetime to UTC.

    SQLite (used in tests) stores `DateTime(timezone=True)` columns as
    text without offsets and returns naive datetimes on load; Postgres
    preserves the offset. Normalising on the way out keeps comparisons
    consistent between the two backends.
    """
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


async def _load_active_session(
    session: AsyncSession, token: str, now: datetime
) -> WebSession | None:
    row = await session.get(WebSession, token)
    if row is None:
        return None
    if now >= _as_utc(row.hard_expires_at) or now >= _as_utc(row.expires_at):
        # Best-effort cleanup; the retention job sweeps stragglers too.
        await session.delete(row)
        await session.commit()
        return None
    return row


def _client_ip(request: Request) -> str | None:
    # FastAPI puts the peer address on `request.client`. We don't trust
    # X-Forwarded-For here because the local-admin path is hit before any
    # production-grade reverse-proxy fronting is wired up; M5b will revisit
    # this once the nginx config trusts a specific upstream.
    client = request.client
    return client.host if client else None


async def require_session(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    cookie_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
) -> SessionContext:
    """FastAPI dep: yield the active SessionContext or raise 401."""
    if not cookie_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="no_session")
    now = datetime.now(UTC)
    row = await _load_active_session(session, cookie_token, now)
    if row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="session_expired")
    # Slide the sliding-window expiry, but never past the hard cap.
    row.last_seen_at = now
    row.expires_at = min(now + SESSION_SLIDING_LIFETIME, _as_utc(row.hard_expires_at))
    await session.commit()
    user_agent = request.headers.get("user-agent")
    return SessionContext(
        token=row.token,
        username=row.username_snapshot,
        role=row.role,
        auth_method=row.auth_method,  # type: ignore[arg-type]
        actor_id=row.local_admin_id,
        client_ip=_client_ip(request),
        user_agent=user_agent,
    )


async def require_admin(
    ctx: Annotated[SessionContext, Depends(require_session)],
) -> SessionContext:
    if ctx.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin_required")
    return ctx
