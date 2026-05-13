"""Internal RPC endpoints consumed by the MAVIS child in the tac_plus-ng container.

Two routes:

- `POST /auth` (M3d) — verify a user's password by binding to AD. Returns
  ACK/NAK/NFD/ERR.
- `POST /info` (M4) — given (username, nas_ip), resolve the device, compute
  the effective PrivilegeProfile, and return a rendered TACPROFILE inline
  script that the daemon evaluates per command.

Both are mounted under `/internal/` so operators can firewall the route to
the docker-internal network — it must never be reachable from the public
reverse proxy.
"""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.ldap_config import resolve_ldap_endpoint
from app.auth.mavis_authn import AuthOutcome, AuthResult, evaluate
from app.authz import (
    evaluate_for_user,
    render_tacprofile,
    resolve_device_for_ip,
)
from app.db.models import Authorization, Device, User
from app.db.session import get_session

router = APIRouter()


class AuthRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=256)
    password: str = Field(..., max_length=1024)


class AuthResponse(BaseModel):
    result: AuthResult
    reason: str | None = None


class InfoRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=256)
    nas_ip: str = Field(..., min_length=1, max_length=64)


class InfoResponse(BaseModel):
    result: AuthResult
    reason: str | None = None
    profile: str | None = None
    """Rendered TACPROFILE inline script, set iff `result == 'ACK'`."""


@router.post("/auth", response_model=AuthResponse)
async def mavis_auth(
    req: AuthRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AuthResponse:
    user = (
        await session.execute(select(User).where(User.sam_account_name == req.username))
    ).scalar_one_or_none()
    endpoint = await resolve_ldap_endpoint(session)

    outcome: AuthOutcome = await asyncio.to_thread(evaluate, user, endpoint, req.password)
    return AuthResponse(result=outcome.result, reason=outcome.reason)


@router.post("/info", response_model=InfoResponse)
async def mavis_info(
    req: InfoRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> InfoResponse:
    user = (
        await session.execute(
            select(User)
            .options(selectinload(User.groups))
            .where(User.sam_account_name == req.username)
        )
    ).scalar_one_or_none()
    if user is None:
        return InfoResponse(result="NFD", reason="unknown_user")
    if not user.enabled:
        return InfoResponse(result="NAK", reason="user_disabled")

    devices = (await session.execute(select(Device))).scalars().all()
    device = resolve_device_for_ip(req.nas_ip, devices)
    if device is None:
        return InfoResponse(result="NAK", reason="unknown_nas")

    authorizations = (
        (
            await session.execute(
                select(Authorization).where(
                    Authorization.device_group_id == device.device_group_id
                )
            )
        )
        .scalars()
        .all()
    )

    outcome = evaluate_for_user(user, device.device_group_id, authorizations)
    if outcome.profile is None:
        return InfoResponse(result="NAK", reason="no_authorization")

    return InfoResponse(result="ACK", profile=render_tacprofile(outcome.profile))
