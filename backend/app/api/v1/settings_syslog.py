"""Syslog forwarder settings (M6c).

Reads / writes the persisted forwarder configuration (host, port,
protocol, facility, hostnames, TLS material). The actual forwarder
loop ticks every POLL_SECONDS and picks up new config on the next
batch — no scheduler restart needed.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append as audit_append
from app.audit.actions import (
    SYSLOG_CONFIG_UPDATED,
    SYSLOG_TEST_FAILED,
    SYSLOG_TEST_SUCCEEDED,
)
from app.auth.sessions import SessionContext, require_session
from app.db.models import SystemSecret, SystemSetting
from app.db.session import get_session
from app.syslog import (
    SETTING_ENABLED,
    SETTING_HOST,
    SETTING_LAST_ID,
    SETTING_PORT,
    SETTING_PROTOCOL,
    load_config,
    send_test_message,
)
from app.syslog.forwarder import (
    SECRET_TLS_CA_PEM,
    SECRET_TLS_CLIENT_CERT_PEM,
    SECRET_TLS_CLIENT_KEY_PEM,
    SETTING_APP_NAME,
    SETTING_FACILITY,
    SETTING_HOSTNAME,
    SETTING_LAST_AUDIT_ID,
    SETTING_LAST_ERROR,
    SETTING_LAST_ERROR_AT,
    SETTING_TLS_SERVER_NAME,
    SETTING_TLS_VERIFY,
)

router = APIRouter()


class SyslogStatusRead(BaseModel):
    enabled: bool
    host: str | None
    port: int
    protocol: Literal["udp", "tcp", "tls"]
    facility: int
    app_name: str
    hostname: str
    tls_verify: bool
    tls_server_name: str | None
    tls_ca_present: bool
    tls_client_cert_present: bool
    tls_client_key_present: bool
    last_forwarded_id: int
    last_audit_id: int
    last_error: str | None
    last_error_at: datetime | None


class SyslogUpdate(BaseModel):
    enabled: bool = False
    host: str = Field(..., min_length=1, max_length=255)
    port: int = Field(default=6514, ge=1, le=65535)
    protocol: Literal["udp", "tcp", "tls"] = "tls"
    facility: int = Field(default=16, ge=0, le=23)
    app_name: str = Field(default="tacacs-web", min_length=1, max_length=48)
    hostname: str = Field(default="tacacs-web", min_length=1, max_length=255)
    tls_verify: bool = True
    tls_server_name: str | None = Field(default=None, max_length=255)
    # Secrets — supplying None keeps the stored value; "" deletes it.
    tls_ca_pem: str | None = None
    tls_client_cert_pem: str | None = None
    tls_client_key_pem: str | None = None


async def _read(session: AsyncSession, key: str) -> str | None:
    row = (
        await session.execute(select(SystemSetting).where(SystemSetting.key == key))
    ).scalar_one_or_none()
    return row.value if row is not None else None


async def _read_secret(session: AsyncSession, key: str) -> str | None:
    row = (
        await session.execute(select(SystemSecret).where(SystemSecret.key == key))
    ).scalar_one_or_none()
    return row.value if row is not None else None


async def _write(session: AsyncSession, key: str, value: str | None) -> None:
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


async def _read_status(session: AsyncSession) -> SyslogStatusRead:
    cfg = await load_config(session)
    last_id_raw = await _read(session, SETTING_LAST_ID) or "0"
    last_id = int(last_id_raw) if last_id_raw.isdigit() else 0
    last_audit_raw = await _read(session, SETTING_LAST_AUDIT_ID) or "0"
    last_audit_id = int(last_audit_raw) if last_audit_raw.isdigit() else 0
    last_error = await _read(session, SETTING_LAST_ERROR)
    last_error_at_raw = await _read(session, SETTING_LAST_ERROR_AT)
    last_error_at: datetime | None = None
    if last_error_at_raw:
        try:
            last_error_at = datetime.fromisoformat(last_error_at_raw)
        except ValueError:
            last_error_at = None
    return SyslogStatusRead(
        enabled=cfg.enabled,
        host=cfg.host or None,
        port=cfg.port,
        protocol=cfg.protocol,
        facility=cfg.facility,
        app_name=cfg.app_name,
        hostname=cfg.hostname,
        tls_verify=cfg.tls_verify,
        tls_server_name=cfg.tls_server_name,
        tls_ca_present=cfg.tls_ca_pem is not None,
        tls_client_cert_present=cfg.tls_client_cert_pem is not None,
        tls_client_key_present=cfg.tls_client_key_pem is not None,
        last_forwarded_id=last_id,
        last_audit_id=last_audit_id,
        last_error=last_error,
        last_error_at=last_error_at,
    )


@router.get("", response_model=SyslogStatusRead)
async def get_status(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SyslogStatusRead:
    return await _read_status(session)


@router.put("", response_model=SyslogStatusRead)
async def update_config(
    payload: SyslogUpdate,
    ctx: Annotated[SessionContext, Depends(require_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SyslogStatusRead:
    if ctx.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="admin_required")
    await _write(session, SETTING_ENABLED, "true" if payload.enabled else "false")
    await _write(session, SETTING_HOST, payload.host.strip())
    await _write(session, SETTING_PORT, str(payload.port))
    await _write(session, SETTING_PROTOCOL, payload.protocol)
    await _write(session, SETTING_FACILITY, str(payload.facility))
    await _write(session, SETTING_APP_NAME, payload.app_name.strip())
    await _write(session, SETTING_HOSTNAME, payload.hostname.strip())
    await _write(session, SETTING_TLS_VERIFY, "true" if payload.tls_verify else "false")
    await _write(
        session, SETTING_TLS_SERVER_NAME, payload.tls_server_name or None
    )

    # Secrets: only touch when explicitly provided. Pass empty string
    # to delete.
    if payload.tls_ca_pem is not None:
        await _write_secret(
            session, SECRET_TLS_CA_PEM, payload.tls_ca_pem or None
        )
    if payload.tls_client_cert_pem is not None:
        await _write_secret(
            session, SECRET_TLS_CLIENT_CERT_PEM, payload.tls_client_cert_pem or None
        )
    if payload.tls_client_key_pem is not None:
        await _write_secret(
            session, SECRET_TLS_CLIENT_KEY_PEM, payload.tls_client_key_pem or None
        )

    await audit_append(
        session,
        actor_username_snapshot=ctx.username,
        actor_role=ctx.role,
        auth_method=ctx.auth_method,
        action=SYSLOG_CONFIG_UPDATED,
        actor_id=ctx.actor_id,
        target_type="syslog",
        summary=json.dumps(
            {
                "enabled": payload.enabled,
                "host": payload.host,
                "port": payload.port,
                "protocol": payload.protocol,
            }
        ),
        client_ip=ctx.client_ip,
        user_agent=ctx.user_agent,
    )
    await session.commit()
    return await _read_status(session)


@router.post("/test")
async def test_endpoint(
    ctx: Annotated[SessionContext, Depends(require_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, str]:
    if ctx.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="admin_required")
    cfg = await load_config(session)
    if not cfg.host:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="syslog.host is not configured"
        )
    import asyncio

    try:
        await asyncio.to_thread(send_test_message, cfg)
    except Exception as exc:
        await audit_append(
            session,
            actor_username_snapshot=ctx.username,
            actor_role=ctx.role,
            auth_method=ctx.auth_method,
            action=SYSLOG_TEST_FAILED,
            actor_id=ctx.actor_id,
            target_type="syslog",
            summary=f"{exc.__class__.__name__}: {exc}",
            client_ip=ctx.client_ip,
            user_agent=ctx.user_agent,
        )
        await session.commit()
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail=f"{exc.__class__.__name__}: {exc}"
        ) from exc

    await audit_append(
        session,
        actor_username_snapshot=ctx.username,
        actor_role=ctx.role,
        auth_method=ctx.auth_method,
        action=SYSLOG_TEST_SUCCEEDED,
        actor_id=ctx.actor_id,
        target_type="syslog",
        summary=f"{cfg.protocol}://{cfg.host}:{cfg.port}",
        client_ip=ctx.client_ip,
        user_agent=ctx.user_agent,
    )
    await session.commit()
    return {"status": "ok"}
