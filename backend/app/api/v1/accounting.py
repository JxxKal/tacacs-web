"""Read-only accounting record endpoint.

Lists rows from `accounting_record` with filters that mirror the
audit-log endpoint plus a few accounting-specific ones (nas_ip,
task_id). Sorted newest-first. Admin-only — accounting payloads
include user activity history that's not for general consumption.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.sessions import SessionContext, require_session
from app.db.models import AccountingRecord
from app.db.session import get_session

router = APIRouter()


class AccountingEntryRead(BaseModel):
    id: int
    ts: datetime
    nas_ip: str | None
    username: str | None
    port: str | None
    nac_ip: str | None
    action: str
    service: str | None
    cmd: str | None
    priv_lvl: int | None
    elapsed_seconds: int | None
    task_id: str | None
    device_id: int | None
    raw_av_pairs: dict[str, str]

    model_config = {"from_attributes": True}


class AccountingPage(BaseModel):
    total: int
    limit: int
    offset: int
    entries: list[AccountingEntryRead]


@router.get("", response_model=AccountingPage)
async def list_accounting(
    ctx: Annotated[SessionContext, Depends(require_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    action: Annotated[str | None, Query(max_length=16)] = None,
    username: Annotated[str | None, Query(max_length=256)] = None,
    nas_ip: Annotated[str | None, Query(max_length=64)] = None,
    task_id: Annotated[str | None, Query(max_length=64)] = None,
    cmd: Annotated[str | None, Query(max_length=512)] = None,
    since: Annotated[datetime | None, Query()] = None,
    until: Annotated[datetime | None, Query()] = None,
) -> AccountingPage:
    if ctx.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="admin_required")

    filters = []
    if action:
        filters.append(AccountingRecord.action == action)
    if username:
        filters.append(AccountingRecord.username.ilike(f"%{username}%"))
    if nas_ip:
        filters.append(AccountingRecord.nas_ip == nas_ip)
    if task_id:
        filters.append(AccountingRecord.task_id == task_id)
    if cmd:
        filters.append(AccountingRecord.cmd.ilike(f"%{cmd}%"))
    if since:
        filters.append(AccountingRecord.ts >= since)
    if until:
        filters.append(AccountingRecord.ts < until)
    where = and_(*filters) if filters else None

    count_stmt = select(func.count()).select_from(AccountingRecord)
    if where is not None:
        count_stmt = count_stmt.where(where)
    total = (await session.execute(count_stmt)).scalar_one()

    rows_stmt = select(AccountingRecord).order_by(AccountingRecord.id.desc())
    if where is not None:
        rows_stmt = rows_stmt.where(where)
    rows_stmt = rows_stmt.limit(limit).offset(offset)
    rows = (await session.execute(rows_stmt)).scalars().all()

    return AccountingPage(
        total=int(total),
        limit=limit,
        offset=offset,
        entries=[AccountingEntryRead.model_validate(r) for r in rows],
    )
