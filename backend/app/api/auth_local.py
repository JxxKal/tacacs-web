"""Local break-glass admin login (ADR-0003).

Mounted under `/login/local` so it sits at a distinct URL from the future
SAML SP endpoints; the UI styles it as emergency-only. Sets the
HttpOnly + Secure + SameSite=Lax session cookie on success; clears it on
logout.

Audit-logs every login attempt (success + failure) and every logout via
the closed action vocabulary in `app.audit.actions`.
"""

from __future__ import annotations

import ipaddress
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append as audit_append
from app.audit.actions import (
    AUTH_LOGIN_FAILED,
    AUTH_LOGIN_SUCCEEDED,
    AUTH_LOGOUT,
)
from app.auth.password import verify_password
from app.auth.sessions import (
    SESSION_COOKIE_NAME,
    SESSION_SLIDING_LIFETIME,
    SessionContext,
    create_session,
    require_session,
    revoke_session,
)
from app.core.config import settings
from app.db.models import LocalAdmin
from app.db.session import get_session

router = APIRouter()


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=1024)


class LoginResponse(BaseModel):
    username: str
    role: str
    auth_method: str


class MeResponse(LoginResponse):
    pass


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent")


def _cidr_allows(cidr: str | None, client_ip: str | None) -> bool:
    if not cidr:
        return True
    if not client_ip:
        return False
    try:
        return ipaddress.ip_address(client_ip) in ipaddress.ip_network(cidr, strict=False)
    except ValueError:
        return False


@router.post("/login/local", response_model=LoginResponse)
async def login_local(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> LoginResponse:
    client_ip = _client_ip(request)
    user_agent = _user_agent(request)
    admin = (
        await session.execute(select(LocalAdmin).where(LocalAdmin.username == payload.username))
    ).scalar_one_or_none()
    accepted = admin is not None and verify_password(
        admin.password_argon2_hash, payload.password
    )
    cidr_ok = admin is None or _cidr_allows(admin.allowed_source_cidr, client_ip)

    if not accepted or not cidr_ok:
        await audit_append(
            session,
            actor_username_snapshot=payload.username,
            actor_role="unknown",
            auth_method="local",
            action=AUTH_LOGIN_FAILED,
            summary="bad_password" if not accepted else "cidr_denied",
            client_ip=client_ip,
            user_agent=user_agent,
        )
        await session.commit()
        # Constant-time-ish: same error for "no such user", "wrong password",
        # "CIDR denied". Don't leak which lever failed.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_credentials"
        )

    assert admin is not None  # narrowed by accepted-check
    ws = await create_session(
        session,
        username=admin.username,
        role="admin",
        auth_method="local",
        actor_id=admin.id,
        client_ip=client_ip,
    )
    admin.last_login_at = ws.created_at
    await audit_append(
        session,
        actor_username_snapshot=admin.username,
        actor_role="admin",
        auth_method="local",
        action=AUTH_LOGIN_SUCCEEDED,
        actor_id=admin.id,
        client_ip=client_ip,
        user_agent=user_agent,
    )
    await session.commit()

    response.set_cookie(
        SESSION_COOKIE_NAME,
        ws.token,
        max_age=int(SESSION_SLIDING_LIFETIME.total_seconds()),
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )
    return LoginResponse(username=admin.username, role="admin", auth_method="local")


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    ctx: Annotated[SessionContext, Depends(require_session)],
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    await revoke_session(session, ctx.token)
    await audit_append(
        session,
        actor_username_snapshot=ctx.username,
        actor_role=ctx.role,
        auth_method=ctx.auth_method,
        action=AUTH_LOGOUT,
        actor_id=ctx.actor_id,
        client_ip=ctx.client_ip,
        user_agent=ctx.user_agent,
    )
    await session.commit()
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")


@router.get("/me", response_model=MeResponse)
async def me(
    ctx: Annotated[SessionContext, Depends(require_session)],
) -> MeResponse:
    return MeResponse(username=ctx.username, role=ctx.role, auth_method=ctx.auth_method)
