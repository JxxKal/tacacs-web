"""Runtime-configurable system settings (LDAPS endpoint, public hostname).

Backed by the `system_setting` key/value table. Each setting category
gets its own typed read/write pair so the UI never sees raw key names
and so server-side validation can be specific per field.

The current settings (M5d) are:
- `ldap.url` — the LDAPS endpoint MAVIS binds to for password verification.
- `web.base_url` — the canonical https://... URL operators reach the UI on.
  Future code (SAML SP callbacks, absolute notification links) consumes it;
  v1 just stores it.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append as audit_append
from app.audit.actions import (
    SETTING_LDAP_URL_UPDATED,
    SETTING_WEB_BASE_URL_UPDATED,
)
from app.auth.sessions import SessionContext, require_session
from app.db.models import SystemSetting
from app.db.session import get_session

router = APIRouter()

LDAP_URL_KEY = "ldap.url"
WEB_BASE_URL_KEY = "web.base_url"


class LdapSettingsRead(BaseModel):
    url: str | None


class LdapSettingsUpdate(BaseModel):
    url: str = Field(..., min_length=1, max_length=512)

    @field_validator("url")
    @classmethod
    def _check_url(cls, value: str) -> str:
        v = value.strip()
        if not (v.startswith("ldap://") or v.startswith("ldaps://")):
            raise ValueError("must start with ldap:// or ldaps://")
        return v


class WebSettingsRead(BaseModel):
    base_url: str | None


class WebSettingsUpdate(BaseModel):
    base_url: str = Field(..., min_length=1, max_length=512)

    @field_validator("base_url")
    @classmethod
    def _check_url(cls, value: str) -> str:
        v = value.strip().rstrip("/")
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("must start with http:// or https://")
        return v


async def _read_setting(session: AsyncSession, key: str) -> str | None:
    row = (
        await session.execute(select(SystemSetting).where(SystemSetting.key == key))
    ).scalar_one_or_none()
    return row.value if row is not None else None


async def _write_setting(session: AsyncSession, key: str, value: str) -> None:
    row = (
        await session.execute(select(SystemSetting).where(SystemSetting.key == key))
    ).scalar_one_or_none()
    if row is None:
        session.add(SystemSetting(key=key, value=value))
    else:
        row.value = value


@router.get("/ldap", response_model=LdapSettingsRead)
async def get_ldap_settings(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> LdapSettingsRead:
    return LdapSettingsRead(url=await _read_setting(session, LDAP_URL_KEY))


@router.put("/ldap", response_model=LdapSettingsRead)
async def put_ldap_settings(
    payload: LdapSettingsUpdate,
    ctx: Annotated[SessionContext, Depends(require_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> LdapSettingsRead:
    if ctx.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="admin_required")
    await _write_setting(session, LDAP_URL_KEY, payload.url)
    await audit_append(
        session,
        actor_username_snapshot=ctx.username,
        actor_role=ctx.role,
        auth_method=ctx.auth_method,
        action=SETTING_LDAP_URL_UPDATED,
        actor_id=ctx.actor_id,
        target_type="system_setting",
        summary=payload.url,
        client_ip=ctx.client_ip,
        user_agent=ctx.user_agent,
    )
    await session.commit()
    return LdapSettingsRead(url=payload.url)


@router.get("/web", response_model=WebSettingsRead)
async def get_web_settings(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> WebSettingsRead:
    return WebSettingsRead(base_url=await _read_setting(session, WEB_BASE_URL_KEY))


@router.put("/web", response_model=WebSettingsRead)
async def put_web_settings(
    payload: WebSettingsUpdate,
    ctx: Annotated[SessionContext, Depends(require_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> WebSettingsRead:
    if ctx.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="admin_required")
    await _write_setting(session, WEB_BASE_URL_KEY, payload.base_url)
    await audit_append(
        session,
        actor_username_snapshot=ctx.username,
        actor_role=ctx.role,
        auth_method=ctx.auth_method,
        action=SETTING_WEB_BASE_URL_UPDATED,
        actor_id=ctx.actor_id,
        target_type="system_setting",
        summary=payload.base_url,
        client_ip=ctx.client_ip,
        user_agent=ctx.user_agent,
    )
    await session.commit()
    return WebSettingsRead(base_url=payload.base_url)
