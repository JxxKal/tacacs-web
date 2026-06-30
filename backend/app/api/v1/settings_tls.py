"""TLS settings endpoints: read current cert info, upload, regenerate.

The on-disk PEMs in the `tls-state` volume are the source of truth; nginx
reads them at (re)start. We persist a status row in `system_setting`
(`tls.source`) so the UI can distinguish "operator uploaded" from
"bootstrap self-signed" without reparsing the cert every request.
"""

from __future__ import annotations

import base64
import binascii
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append as audit_append
from app.audit.actions import (
    TLS_CERT_REGENERATED,
    TLS_CERT_UPLOADED,
    TLS_PFX_UPLOADED,
)
from app.auth.sessions import SessionContext, require_session
from app.db.models import SystemSetting
from app.db.session import get_session
from app.tls import (
    CertInfo,
    generate_self_signed,
    parse_cert,
    parse_pkcs12,
    validate_cert_key_pair,
    write_cert_and_key,
)
from app.tls.certs import CERT_FILE, CertError

router = APIRouter()

TLS_SOURCE_KEY = "tls.source"


class CertInfoRead(BaseModel):
    subject_cn: str | None
    issuer_cn: str | None
    san_dns: list[str]
    not_before: datetime
    not_after: datetime
    fingerprint_sha256: str
    is_self_signed: bool
    source: str  # "uploaded" | "bootstrap" | "self_signed_via_ui"


class TlsStatusRead(BaseModel):
    has_cert: bool
    info: CertInfoRead | None


class CertUploadBody(BaseModel):
    cert_pem: str = Field(..., min_length=1, max_length=64_000)
    key_pem: str = Field(..., min_length=1, max_length=64_000)


class RegenerateBody(BaseModel):
    common_name: str = Field(..., min_length=1, max_length=253)
    days: int = Field(default=825, ge=1, le=3650)


class PfxUploadBody(BaseModel):
    """Operator-uploaded PKCS#12 / PFX, typically a Windows AD CS export.

    `pfx_base64` is the binary PFX wrapped in base64 so we can ship it as
    JSON. Cap on size guards against multi-MB enrolments — a normal AD-CS
    export with leaf + chain sits at low single-digit kilobytes.
    """

    pfx_base64: str = Field(..., min_length=1, max_length=400_000)
    password: str | None = Field(default=None, max_length=512)


def _to_read(info: CertInfo, source: str) -> CertInfoRead:
    return CertInfoRead(
        subject_cn=info.subject_cn,
        issuer_cn=info.issuer_cn,
        san_dns=list(info.san_dns),
        not_before=info.not_before,
        not_after=info.not_after,
        fingerprint_sha256=info.fingerprint_sha256,
        is_self_signed=info.is_self_signed,
        source=source,
    )


async def _read_source(session: AsyncSession) -> str:
    row = (
        await session.execute(select(SystemSetting).where(SystemSetting.key == TLS_SOURCE_KEY))
    ).scalar_one_or_none()
    return row.value if row is not None else "bootstrap"


async def _write_source(session: AsyncSession, value: str) -> None:
    row = (
        await session.execute(select(SystemSetting).where(SystemSetting.key == TLS_SOURCE_KEY))
    ).scalar_one_or_none()
    if row is None:
        session.add(SystemSetting(key=TLS_SOURCE_KEY, value=value))
    else:
        row.value = value


@router.get("", response_model=TlsStatusRead)
async def get_tls_status(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TlsStatusRead:
    if not CERT_FILE.exists():
        return TlsStatusRead(has_cert=False, info=None)
    try:
        info = parse_cert(CERT_FILE.read_bytes())
    except CertError:
        return TlsStatusRead(has_cert=False, info=None)
    source = await _read_source(session)
    return TlsStatusRead(has_cert=True, info=_to_read(info, source))


@router.post("/upload", response_model=TlsStatusRead)
async def upload_tls(
    payload: CertUploadBody,
    ctx: Annotated[SessionContext, Depends(require_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TlsStatusRead:
    if ctx.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="admin_required")
    cert_pem = payload.cert_pem.encode("utf-8")
    key_pem = payload.key_pem.encode("utf-8")
    try:
        validate_cert_key_pair(cert_pem, key_pem)
        info = parse_cert(cert_pem)
    except CertError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    try:
        write_cert_and_key(cert_pem, key_pem)
    except OSError as exc:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"could not write to tls-state volume: {exc}",
        ) from exc
    await _write_source(session, "uploaded")
    await audit_append(
        session,
        actor_username_snapshot=ctx.username,
        actor_role=ctx.role,
        auth_method=ctx.auth_method,
        action=TLS_CERT_UPLOADED,
        actor_id=ctx.actor_id,
        target_type="tls_cert",
        summary=f"{info.subject_cn or '?'} (sha256 {info.fingerprint_sha256[:23]}…)",
        client_ip=ctx.client_ip,
        user_agent=ctx.user_agent,
    )
    await session.commit()
    return TlsStatusRead(has_cert=True, info=_to_read(info, "uploaded"))


@router.post("/upload-pfx", response_model=TlsStatusRead)
async def upload_tls_pfx(
    payload: PfxUploadBody,
    ctx: Annotated[SessionContext, Depends(require_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TlsStatusRead:
    """Accept a PFX/PKCS#12 export (typical for Windows AD CS).

    Extracts the leaf cert + any chain certs (intermediates) and the
    private key, writes the chained PEM + unencrypted key to the
    tls-state volume. nginx serves the full chain on its next restart.
    """
    if ctx.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="admin_required")
    try:
        pfx_bytes = base64.b64decode(payload.pfx_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="invalid_base64") from exc
    try:
        cert_pem, key_pem = parse_pkcs12(pfx_bytes, payload.password)
        info = parse_cert(cert_pem)
    except CertError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    try:
        write_cert_and_key(cert_pem, key_pem)
    except OSError as exc:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"could not write to tls-state volume: {exc}",
        ) from exc
    await _write_source(session, "uploaded")
    await audit_append(
        session,
        actor_username_snapshot=ctx.username,
        actor_role=ctx.role,
        auth_method=ctx.auth_method,
        action=TLS_PFX_UPLOADED,
        actor_id=ctx.actor_id,
        target_type="tls_cert",
        summary=f"PFX: {info.subject_cn or '?'} (sha256 {info.fingerprint_sha256[:23]}…)",
        client_ip=ctx.client_ip,
        user_agent=ctx.user_agent,
    )
    await session.commit()
    return TlsStatusRead(has_cert=True, info=_to_read(info, "uploaded"))


@router.post("/regenerate-self-signed", response_model=TlsStatusRead)
async def regenerate_self_signed(
    payload: RegenerateBody,
    ctx: Annotated[SessionContext, Depends(require_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TlsStatusRead:
    if ctx.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="admin_required")
    cert_pem, key_pem = generate_self_signed(payload.common_name, days=payload.days)
    try:
        write_cert_and_key(cert_pem, key_pem)
    except OSError as exc:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"could not write to tls-state volume: {exc}",
        ) from exc
    info = parse_cert(cert_pem)
    await _write_source(session, "self_signed_via_ui")
    await audit_append(
        session,
        actor_username_snapshot=ctx.username,
        actor_role=ctx.role,
        auth_method=ctx.auth_method,
        action=TLS_CERT_REGENERATED,
        actor_id=ctx.actor_id,
        target_type="tls_cert",
        summary=f"CN={payload.common_name}, {payload.days}d",
        client_ip=ctx.client_ip,
        user_agent=ctx.user_agent,
    )
    await session.commit()
    return TlsStatusRead(has_cert=True, info=_to_read(info, "self_signed_via_ui"))
