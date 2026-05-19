"""AD-Sync settings + test + manual-run endpoints.

Reads + writes the worker's config (URL, bind DN, base DNs, filter,
cadence, enabled). Plus:

- POST /test: open a one-shot LDAPS bind with the stored creds (or
  override creds from the body) to verify the service account.
- POST /run: trigger one full sync immediately; returns the run summary.

`web.base_url`-style 403 for non-admin writers. Each operation audits
to a dedicated action code.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append as audit_append
from app.audit.actions import (
    LDAP_SYNC_CONFIG_UPDATED,
    LDAP_SYNC_RUN_FAILED,
    LDAP_SYNC_RUN_SUCCEEDED,
    LDAP_SYNC_TEST_FAILED,
    LDAP_SYNC_TEST_SUCCEEDED,
)
from app.auth.sessions import SessionContext, require_session
from app.db.models import SystemSecret, SystemSetting
from app.db.session import SyncSessionLocal, get_session
from app.ldap_sync import scheduler as ldap_scheduler
from app.ldap_sync.worker import (
    CADENCE_DEFAULT_SECONDS,
    CADENCE_MIN_SECONDS,
    SECRET_BIND_PASSWORD,
    SETTING_BASE_DNS,
    SETTING_BIND_DN,
    SETTING_CADENCE,
    SETTING_ENABLED,
    SETTING_LAST_RESULT,
    SETTING_LDAP_URL,
    SETTING_USER_FILTER,
    SyncRunError,
    load_bind_password,
    load_config,
    run_full_sync,
    test_connection,
)

router = APIRouter()


class LastSyncRead(BaseModel):
    started_at: str
    finished_at: str | None
    users_seen: int
    users_inserted: int
    users_updated: int
    users_disabled: int
    groups_seen: int
    error: str | None


class LdapSyncStatusRead(BaseModel):
    configured: bool
    url: str | None
    bind_dn: str | None
    bind_password_set: bool
    base_dns: list[str]
    user_filter: str | None
    cadence_seconds: int
    enabled: bool
    last_sync: LastSyncRead | None


class LdapSyncUpdate(BaseModel):
    url: str | None = Field(default=None, max_length=512)
    bind_dn: str = Field(..., min_length=1, max_length=1024)
    bind_password: str | None = Field(default=None, max_length=1024)
    """Plain password. Omitted on PUT keeps the stored one."""
    base_dns: list[str] = Field(..., min_length=1)
    user_filter: str | None = Field(default=None, max_length=2048)
    cadence_seconds: int = Field(default=CADENCE_DEFAULT_SECONDS, ge=CADENCE_MIN_SECONDS)
    enabled: bool = False

    @field_validator("url")
    @classmethod
    def _check_url(cls, v: str | None) -> str | None:
        if v is None or not v.strip():
            return None
        url = v.strip()
        if not (url.startswith("ldap://") or url.startswith("ldaps://")):
            raise ValueError("url must start with ldap:// or ldaps://")
        return url

    @field_validator("base_dns")
    @classmethod
    def _check_base_dns(cls, v: list[str]) -> list[str]:
        cleaned = [s.strip() for s in v if s and s.strip()]
        if not cleaned:
            raise ValueError("at least one base DN required")
        return cleaned


class TestConnectionBody(BaseModel):
    """Optional overrides so the operator can dry-run new creds before saving."""

    url: str | None = Field(default=None, max_length=512)
    bind_dn: str | None = Field(default=None, max_length=1024)
    bind_password: str | None = Field(default=None, max_length=1024)


# --------------- helpers --------------------------------------------------


def _read(session_sync, key: str) -> str | None:  # type: ignore[no-untyped-def]
    row = session_sync.execute(
        select(SystemSetting).where(SystemSetting.key == key)
    ).scalar_one_or_none()
    return row.value if row is not None else None


async def _write_setting(session: AsyncSession, key: str, value: str | None) -> None:
    row = (
        await session.execute(select(SystemSetting).where(SystemSetting.key == key))
    ).scalar_one_or_none()
    if value is None:
        if row is not None:
            await session.delete(row)
        return
    if row is None:
        session.add(SystemSetting(key=key, value=value))
    else:
        row.value = value


async def _write_secret(session: AsyncSession, key: str, value: str | None) -> None:
    row = (
        await session.execute(select(SystemSecret).where(SystemSecret.key == key))
    ).scalar_one_or_none()
    if value is None:
        if row is not None:
            await session.delete(row)
        return
    if row is None:
        session.add(SystemSecret(key=key, value=value))
    else:
        row.value = value


def _load_status_sync() -> LdapSyncStatusRead:
    with SyncSessionLocal() as s:
        url = _read(s, SETTING_LDAP_URL)
        bind_dn = _read(s, SETTING_BIND_DN)
        base_dns_raw = _read(s, SETTING_BASE_DNS) or "[]"
        try:
            base_dns = [b for b in json.loads(base_dns_raw) if isinstance(b, str)]
        except json.JSONDecodeError:
            base_dns = []
        user_filter = _read(s, SETTING_USER_FILTER)
        cadence_raw = _read(s, SETTING_CADENCE)
        cadence = int(cadence_raw) if cadence_raw and cadence_raw.isdigit() else CADENCE_DEFAULT_SECONDS
        enabled = (_read(s, SETTING_ENABLED) or "false").lower() == "true"
        bind_pw_set = load_bind_password(s) is not None
        last_raw = _read(s, SETTING_LAST_RESULT)
        last: LastSyncRead | None = None
        if last_raw:
            try:
                last = LastSyncRead.model_validate_json(last_raw)
            except ValueError:
                last = None

    configured = bool(url and bind_dn and bind_pw_set and base_dns)
    return LdapSyncStatusRead(
        configured=configured,
        url=url,
        bind_dn=bind_dn,
        bind_password_set=bind_pw_set,
        base_dns=base_dns,
        user_filter=user_filter,
        cadence_seconds=cadence,
        enabled=enabled,
        last_sync=last,
    )


# --------------- routes ---------------------------------------------------


@router.get("", response_model=LdapSyncStatusRead)
async def get_status() -> LdapSyncStatusRead:
    return await asyncio.to_thread(_load_status_sync)


@router.put("", response_model=LdapSyncStatusRead)
async def update_config(
    payload: LdapSyncUpdate,
    ctx: Annotated[SessionContext, Depends(require_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> LdapSyncStatusRead:
    if ctx.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="admin_required")

    await _write_setting(session, SETTING_LDAP_URL, payload.url)
    await _write_setting(session, SETTING_BIND_DN, payload.bind_dn.strip())
    await _write_setting(session, SETTING_BASE_DNS, json.dumps(payload.base_dns))
    await _write_setting(
        session,
        SETTING_USER_FILTER,
        (payload.user_filter or "").strip() or None,
    )
    await _write_setting(session, SETTING_CADENCE, str(payload.cadence_seconds))
    await _write_setting(session, SETTING_ENABLED, "true" if payload.enabled else "false")
    if payload.bind_password is not None and payload.bind_password != "":
        await _write_secret(session, SECRET_BIND_PASSWORD, payload.bind_password)

    await audit_append(
        session,
        actor_username_snapshot=ctx.username,
        actor_role=ctx.role,
        auth_method=ctx.auth_method,
        action=LDAP_SYNC_CONFIG_UPDATED,
        actor_id=ctx.actor_id,
        target_type="ldap_sync",
        summary=(
            f"bind_dn={payload.bind_dn}, base_dns={len(payload.base_dns)}, "
            f"cadence={payload.cadence_seconds}s, enabled={payload.enabled}"
        ),
        client_ip=ctx.client_ip,
        user_agent=ctx.user_agent,
    )
    await session.commit()
    await asyncio.to_thread(ldap_scheduler.refresh_from_db)
    return await asyncio.to_thread(_load_status_sync)


@router.post("/test")
async def test_endpoint(
    payload: TestConnectionBody,
    ctx: Annotated[SessionContext, Depends(require_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, str]:
    if ctx.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="admin_required")

    status_now = await asyncio.to_thread(_load_status_sync)
    url = payload.url or status_now.url
    bind_dn = payload.bind_dn or status_now.bind_dn
    if payload.bind_password and payload.bind_password.strip():
        bind_password: str | None = payload.bind_password
    else:
        bind_password = await asyncio.to_thread(_load_stored_password)

    if not (url and bind_dn and bind_password):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="url, bind_dn, and bind_password required",
        )

    try:
        await asyncio.to_thread(test_connection, url, bind_dn, bind_password)
    except SyncRunError as exc:
        await audit_append(
            session,
            actor_username_snapshot=ctx.username,
            actor_role=ctx.role,
            auth_method=ctx.auth_method,
            action=LDAP_SYNC_TEST_FAILED,
            actor_id=ctx.actor_id,
            target_type="ldap_sync",
            summary=str(exc),
            client_ip=ctx.client_ip,
            user_agent=ctx.user_agent,
        )
        await session.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    await audit_append(
        session,
        actor_username_snapshot=ctx.username,
        actor_role=ctx.role,
        auth_method=ctx.auth_method,
        action=LDAP_SYNC_TEST_SUCCEEDED,
        actor_id=ctx.actor_id,
        target_type="ldap_sync",
        summary=f"bind_dn={bind_dn}",
        client_ip=ctx.client_ip,
        user_agent=ctx.user_agent,
    )
    await session.commit()
    return {"status": "ok"}


@router.post("/run", response_model=LdapSyncStatusRead)
async def run_now(
    ctx: Annotated[SessionContext, Depends(require_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> LdapSyncStatusRead:
    if ctx.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="admin_required")

    started = datetime.utcnow()
    try:
        summary = await asyncio.to_thread(_run_sync_in_thread)
    except SyncRunError as exc:
        await audit_append(
            session,
            actor_username_snapshot=ctx.username,
            actor_role=ctx.role,
            auth_method=ctx.auth_method,
            action=LDAP_SYNC_RUN_FAILED,
            actor_id=ctx.actor_id,
            target_type="ldap_sync",
            summary=f"{exc}",
            client_ip=ctx.client_ip,
            user_agent=ctx.user_agent,
        )
        await session.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    await audit_append(
        session,
        actor_username_snapshot=ctx.username,
        actor_role=ctx.role,
        auth_method=ctx.auth_method,
        action=LDAP_SYNC_RUN_SUCCEEDED,
        actor_id=ctx.actor_id,
        target_type="ldap_sync",
        summary=(
            f"users_seen={summary.users_seen}, inserted={summary.users_inserted}, "
            f"updated={summary.users_updated}, disabled={summary.users_disabled}, "
            f"groups={summary.groups_seen}, took="
            f"{(datetime.utcnow() - started).total_seconds():.2f}s"
        ),
        client_ip=ctx.client_ip,
        user_agent=ctx.user_agent,
    )
    await session.commit()
    return await asyncio.to_thread(_load_status_sync)


# --------------- thread-runners -------------------------------------------


def _load_stored_password() -> str | None:
    with SyncSessionLocal() as s:
        return load_bind_password(s)


def _run_sync_in_thread():  # type: ignore[no-untyped-def]
    from app.ldap_sync.worker import LdapSyncRunSummary

    with SyncSessionLocal() as s:
        cfg = load_config(s)
        if cfg is None:
            raise SyncRunError("LDAP sync is not configured")
        try:
            summary: LdapSyncRunSummary = run_full_sync(s)
        except SyncRunError:
            s.rollback()
            raise
        s.commit()
        return summary
