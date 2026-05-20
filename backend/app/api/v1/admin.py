"""Admin-only maintenance endpoints.

Currently:
- POST /api/v1/admin/regenerate-nas-config: force-rewrite the
  tac_plus-ng hosts.cfg from the current Device table. Normally
  triggered automatically after every Device mutate; this endpoint
  exists so an operator can manually reconcile after editing rows
  via psql or after restoring from a backup.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append as audit_append
from app.audit.actions import NAS_CONFIG_REGENERATED
from app.auth.sessions import SessionContext, require_session
from app.db.session import get_session
from app.nas_config import HOSTS_FILE, regenerate_nas_config

router = APIRouter()


class RegenerateResponse(BaseModel):
    path: str
    bytes_written: int


@router.post("/regenerate-nas-config", response_model=RegenerateResponse)
async def regenerate(
    ctx: Annotated[SessionContext, Depends(require_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RegenerateResponse:
    if ctx.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="admin_required")
    try:
        content = await regenerate_nas_config(session)
    except OSError as exc:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"could not write to shared tac_plus-ng volume: {exc}",
        ) from exc
    await audit_append(
        session,
        actor_username_snapshot=ctx.username,
        actor_role=ctx.role,
        auth_method=ctx.auth_method,
        action=NAS_CONFIG_REGENERATED,
        actor_id=ctx.actor_id,
        target_type="nas_config",
        summary=f"wrote {len(content)} bytes to {HOSTS_FILE}",
        client_ip=ctx.client_ip,
        user_agent=ctx.user_agent,
    )
    await session.commit()
    return RegenerateResponse(path=str(HOSTS_FILE), bytes_written=len(content))
