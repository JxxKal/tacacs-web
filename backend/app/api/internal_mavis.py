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

Each call also writes an audit-log row so the Web-UI Audit-Log page can
show operators what's happening on the live-auth pipeline.
"""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.audit import append as audit_append
from app.audit.actions import (
    TACACS_AUTHN_FAILED,
    TACACS_AUTHN_SUCCEEDED,
    TACACS_AUTHZ_FAILED,
    TACACS_AUTHZ_SUCCEEDED,
)
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
    nas_ip: str | None = Field(default=None, max_length=64)
    """NAS source IP, sent by the MAVIS child since the M5+ audit-log
    work. Optional for backwards compatibility with older mavis_child
    builds in the same compose."""


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

    is_ack = outcome.result == "ACK"
    await audit_append(
        session,
        actor_username_snapshot=req.username,
        actor_role="tacacs_user",
        auth_method="tacacs",
        action=TACACS_AUTHN_SUCCEEDED if is_ack else TACACS_AUTHN_FAILED,
        target_type="nas",
        summary=outcome.reason if not is_ack else None,
        client_ip=req.nas_ip,
        user_agent=None,
        actor_id=user.id if user is not None else None,
    )
    await session.commit()

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

    response, reason, target_id, summary_detail = await _resolve_info(session, req, user)

    is_ack = response.result == "ACK"
    await audit_append(
        session,
        actor_username_snapshot=req.username,
        actor_role="tacacs_user",
        auth_method="tacacs",
        action=TACACS_AUTHZ_SUCCEEDED if is_ack else TACACS_AUTHZ_FAILED,
        target_type="device" if target_id is not None else "nas",
        target_id=target_id,
        summary=summary_detail if is_ack else reason,
        client_ip=req.nas_ip,
        user_agent=None,
        actor_id=user.id if user is not None else None,
    )
    await session.commit()

    return response


async def _resolve_info(
    session: AsyncSession, req: InfoRequest, user: User | None
) -> tuple[InfoResponse, str | None, int | None, str | None]:
    """Return (response, audit_reason, target_id, audit_summary_on_ack).

    Audit data is computed here so the caller's audit_append has the
    right context without re-walking the DB.
    """
    if user is None:
        return (
            InfoResponse(result="NFD", reason="unknown_user"),
            "unknown_user",
            None,
            None,
        )
    if not user.enabled:
        return (
            InfoResponse(result="NAK", reason="user_disabled"),
            "user_disabled",
            None,
            None,
        )

    devices = (await session.execute(select(Device))).scalars().all()
    device = resolve_device_for_ip(req.nas_ip, devices)
    if device is None:
        return (
            InfoResponse(result="NAK", reason="unknown_nas"),
            "unknown_nas",
            None,
            None,
        )

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
        return (
            InfoResponse(result="NAK", reason="no_authorization"),
            "no_authorization",
            device.id,
            None,
        )

    profile_text = render_tacprofile(outcome.profile)
    summary = f"device={device.name}, profile={outcome.profile.name}"
    return (
        InfoResponse(result="ACK", profile=profile_text),
        None,
        device.id,
        summary,
    )
