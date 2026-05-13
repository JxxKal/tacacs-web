"""Single insertion path for the append-only audit log.

Callers go through `append`, never instantiate `AuditLog` directly, so the
"no UPDATE / no DELETE" invariant from ADR-0009 has exactly one place to
audit. Caller is responsible for committing the session — we don't commit
here so the audit row lands in the same transaction as the action it
records.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.actions import ALL_ACTIONS
from app.db.models import AuditLog


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
        raise ValueError(
            f"unknown audit action {action!r}; add it to app.audit.actions"
        )
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
