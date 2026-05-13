"""Internal RPC endpoint consumed by the MAVIS child in the tac_plus-ng container.

The MAVIS child POSTs each AUTH packet here; the backend resolves the user
against the local DB, picks the configured LDAPEndpoint, and verifies the
password by binding to AD. The endpoint is mounted under `/internal/` so
operators can firewall it to the docker-internal network — it must never
be reachable from the public reverse proxy.

This route ships as part of M3d. Per-user/per-device authorization (the
INFO path) lives in M4; M3d only handles the AUTH verdict.
"""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.ldap_config import resolve_ldap_endpoint
from app.auth.mavis_authn import AuthOutcome, AuthResult, evaluate
from app.db.models import User
from app.db.session import get_session

router = APIRouter()


class AuthRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=256)
    password: str = Field(..., max_length=1024)


class AuthResponse(BaseModel):
    result: AuthResult
    reason: str | None = None


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
