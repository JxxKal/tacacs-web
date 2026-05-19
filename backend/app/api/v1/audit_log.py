"""Read-only audit-log endpoint.

Lists rows from `audit_log` with optional filtering by action, username,
auth_method, and time range. Sorted newest-first. ADR-0009 declares
the table append-only, so this endpoint only ever reads.

UI uses this for the Audit-Log page (Web-UI auth events, CRUD events,
TACACS+ live-auth events).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.actions import ALL_ACTIONS
from app.auth.sessions import SessionContext, require_session
from app.db.models import AuditLog
from app.db.session import get_session

router = APIRouter()


class AuditLogEntryRead(BaseModel):
    id: int
    ts: datetime
    actor_id: int | None
    actor_username_snapshot: str
    actor_role: str
    auth_method: str
    action: str
    target_type: str | None
    target_id: int | None
    summary: str | None
    client_ip: str | None
    user_agent: str | None

    model_config = {"from_attributes": True}


class AuditLogPage(BaseModel):
    total: int
    limit: int
    offset: int
    entries: list[AuditLogEntryRead]


class AuditLogActions(BaseModel):
    actions: list[str]


@router.get("/actions", response_model=AuditLogActions)
async def list_known_actions(
    _: Annotated[SessionContext, Depends(require_session)],
) -> AuditLogActions:
    """Closed action vocabulary (ADR-0009) for the UI's filter dropdown."""
    return AuditLogActions(actions=sorted(ALL_ACTIONS))


@router.get("", response_model=AuditLogPage)
async def list_audit_log(
    ctx: Annotated[SessionContext, Depends(require_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    action: Annotated[str | None, Query(max_length=64)] = None,
    username: Annotated[str | None, Query(max_length=256)] = None,
    auth_method: Annotated[str | None, Query(max_length=16)] = None,
    since: Annotated[datetime | None, Query()] = None,
    until: Annotated[datetime | None, Query()] = None,
) -> AuditLogPage:
    if ctx.role != "admin":
        # Per ADR-0009: only admin can browse. Operators / viewers don't
        # see the audit log directly.
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="admin_required")

    filters = []
    if action:
        filters.append(AuditLog.action == action)
    if username:
        filters.append(AuditLog.actor_username_snapshot.ilike(f"%{username}%"))
    if auth_method:
        filters.append(AuditLog.auth_method == auth_method)
    if since:
        filters.append(AuditLog.ts >= since)
    if until:
        filters.append(AuditLog.ts < until)
    where = and_(*filters) if filters else None

    count_stmt = select(func.count()).select_from(AuditLog)
    if where is not None:
        count_stmt = count_stmt.where(where)
    total = (await session.execute(count_stmt)).scalar_one()

    rows_stmt = select(AuditLog).order_by(AuditLog.id.desc())
    if where is not None:
        rows_stmt = rows_stmt.where(where)
    rows_stmt = rows_stmt.limit(limit).offset(offset)
    rows = (await session.execute(rows_stmt)).scalars().all()

    return AuditLogPage(
        total=int(total),
        limit=limit,
        offset=offset,
        entries=[AuditLogEntryRead.model_validate(r) for r in rows],
    )
