"""Single insertion path for the append-only audit log.

Callers go through `append`, never instantiate `AuditLog` directly, so the
"no UPDATE / no DELETE" invariant from ADR-0009 has exactly one place to
audit. Caller is responsible for committing the session — we don't commit
here so the audit row lands in the same transaction as the action it
records.

`append_crud` is a thin wrapper for the most common shape (mutating a
domain resource as the currently-authenticated UI session); it pulls
actor / auth fields off the SessionContext so the handlers stay compact.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.actions import ALL_ACTIONS
from app.db.models import AuditLog

if TYPE_CHECKING:
    from app.auth.sessions import SessionContext


async def append(
    session: AsyncSession,
    *,
    actor_username_snapshot: str,
    actor_role: str,
    auth_method: str,
    action: str,
    target_type: str | None = None,
    target_id: int | None = None,
    summary: str | None = None,
    client_ip: str | None = None,
    user_agent: str | None = None,
    actor_id: int | None = None,
    ts: datetime | None = None,
) -> AuditLog:
    """Insert one audit row. Returns the row but does not commit."""
    if action not in ALL_ACTIONS:
        raise ValueError(f"unknown audit action {action!r}; add it to app.audit.actions")
    row = AuditLog(
        ts=ts or datetime.now(UTC),
        actor_id=actor_id,
        actor_username_snapshot=actor_username_snapshot,
        actor_role=actor_role,
        auth_method=auth_method,
        action=action,
        target_type=target_type,
        target_id=target_id,
        summary=summary,
        client_ip=client_ip,
        user_agent=user_agent,
    )
    session.add(row)
    return row


async def append_crud(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    action: str,
    target_type: str,
    target_id: int,
    summary: str | None = None,
) -> AuditLog:
    """Audit-row helper for CRUD handlers: actor info pulled from `ctx`."""
    return await append(
        session,
        actor_username_snapshot=ctx.username,
        actor_role=ctx.role,
        auth_method=ctx.auth_method,
        action=action,
        actor_id=ctx.actor_id,
        target_type=target_type,
        target_id=target_id,
        summary=summary,
        client_ip=ctx.client_ip,
        user_agent=ctx.user_agent,
    )
