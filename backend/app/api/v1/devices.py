"""CRUD for Device. Includes the rotate-secret flow from ADR-0007."""

from __future__ import annotations

import ipaddress
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append_crud
from app.audit.actions import (
    DEVICE_CREATED,
    DEVICE_DELETED,
    DEVICE_PREVIOUS_RETIRED,
    DEVICE_SECRET_ROTATED,
    DEVICE_UPDATED,
)
from app.auth.sessions import SessionContext, require_session
from app.db.models import Device, DeviceGroup
from app.db.session import get_session
from app.nas_config import regenerate_nas_config

router = APIRouter()


async def _regen(session: AsyncSession) -> None:
    """Re-render the tac_plus-ng hosts.cfg after every Device mutate.

    Swallows write errors so a CRUD success isn't undone by a missing
    shared volume in a dev / test setup. The regen-failure surfaces in
    backend logs and via the manual admin endpoint.
    """
    try:
        await regenerate_nas_config(session)
    except OSError as exc:
        import structlog

        structlog.get_logger("nas_config").warning(
            "nas_config.regen_write_failed", error=str(exc)
        )


def _validate_ip_or_cidr(value: str) -> str:
    try:
        ipaddress.ip_network(value, strict=False)
    except ValueError as exc:
        raise ValueError(f"invalid IP or CIDR: {exc}") from exc
    return value


class DeviceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    ip_or_cidr: str = Field(..., min_length=1, max_length=64)
    device_group_id: int
    current_secret: str | None = Field(default=None, max_length=512)
    description: str | None = Field(default=None, max_length=2048)

    @field_validator("ip_or_cidr")
    @classmethod
    def _check_ip(cls, value: str) -> str:
        return _validate_ip_or_cidr(value)


class DeviceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    ip_or_cidr: str | None = Field(default=None, min_length=1, max_length=64)
    device_group_id: int | None = None
    description: str | None = Field(default=None, max_length=2048)
    current_secret: str | None = Field(default=None, max_length=512)
    """Optional plaintext shared secret. When non-empty, overwrites
    `current_secret_enc` directly — a deliberate hard set, not a rotation:
    the operator changes the secret on the device by hand anyway, so the
    previous-secret overlap window (`/rotate-secret`, ADR-0007) doesn't
    apply. `None` / empty means leave the stored secret untouched."""

    @field_validator("ip_or_cidr")
    @classmethod
    def _check_ip(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return _validate_ip_or_cidr(value)


class DeviceRotateSecret(BaseModel):
    new_secret: str = Field(..., min_length=1, max_length=512)


class DeviceRead(BaseModel):
    id: int
    name: str
    ip_or_cidr: str
    device_group_id: int
    has_current_secret: bool
    has_previous_secret: bool
    previous_retired_at: datetime | None
    description: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_row(cls, row: Device) -> DeviceRead:
        return cls(
            id=row.id,
            name=row.name,
            ip_or_cidr=row.ip_or_cidr,
            device_group_id=row.device_group_id,
            has_current_secret=row.current_secret_enc is not None,
            has_previous_secret=row.previous_secret_enc is not None,
            previous_retired_at=row.previous_retired_at,
            description=row.description,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


async def _ensure_device_group_exists(session: AsyncSession, device_group_id: int) -> None:
    if await session.get(DeviceGroup, device_group_id) is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="unknown_device_group_id"
        )


@router.get("", response_model=list[DeviceRead])
async def list_devices(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[DeviceRead]:
    rows = (await session.execute(select(Device).order_by(Device.id))).scalars().all()
    return [DeviceRead.from_row(r) for r in rows]


@router.post("", response_model=DeviceRead, status_code=status.HTTP_201_CREATED)
async def create_device(
    payload: DeviceCreate,
    ctx: Annotated[SessionContext, Depends(require_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DeviceRead:
    await _ensure_device_group_exists(session, payload.device_group_id)
    row = Device(
        name=payload.name,
        ip_or_cidr=payload.ip_or_cidr,
        device_group_id=payload.device_group_id,
        description=payload.description,
        current_secret_enc=payload.current_secret,
    )
    session.add(row)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="name_or_ip_already_exists"
        ) from exc
    await append_crud(
        session, ctx,
        action=DEVICE_CREATED,
        target_type="device", target_id=row.id,
        summary=f"{row.name} {row.ip_or_cidr}",
    )
    await session.commit()
    await session.refresh(row)
    await _regen(session)
    return DeviceRead.from_row(row)


@router.get("/{device_id}", response_model=DeviceRead)
async def get_device(
    device_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DeviceRead:
    row = await session.get(Device, device_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return DeviceRead.from_row(row)


@router.patch("/{device_id}", response_model=DeviceRead)
async def update_device(
    device_id: int,
    payload: DeviceUpdate,
    ctx: Annotated[SessionContext, Depends(require_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DeviceRead:
    row = await session.get(Device, device_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    changed: list[str] = []
    if payload.device_group_id is not None and payload.device_group_id != row.device_group_id:
        await _ensure_device_group_exists(session, payload.device_group_id)
        changed.append(f"dg {row.device_group_id}->{payload.device_group_id}")
        row.device_group_id = payload.device_group_id
    if payload.name is not None and payload.name != row.name:
        changed.append(f"name {row.name!r}->{payload.name!r}")
        row.name = payload.name
    if payload.ip_or_cidr is not None and payload.ip_or_cidr != row.ip_or_cidr:
        changed.append(f"ip {row.ip_or_cidr}->{payload.ip_or_cidr}")
        row.ip_or_cidr = payload.ip_or_cidr
    if payload.description is not None:
        changed.append("description")
        row.description = payload.description
    if payload.current_secret:
        # Hard set — never log the value itself, only that it changed.
        row.current_secret_enc = payload.current_secret
        changed.append("secret")
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="name_or_ip_already_exists"
        ) from exc
    await append_crud(
        session, ctx,
        action=DEVICE_UPDATED,
        target_type="device", target_id=row.id,
        summary=f"{row.name}: {', '.join(changed) or 'no-op'}",
    )
    await session.commit()
    await session.refresh(row)
    await _regen(session)
    return DeviceRead.from_row(row)


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device(
    device_id: int,
    ctx: Annotated[SessionContext, Depends(require_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    row = await session.get(Device, device_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    name, row_id, ip = row.name, row.id, row.ip_or_cidr
    await session.delete(row)
    await append_crud(
        session, ctx,
        action=DEVICE_DELETED,
        target_type="device", target_id=row_id,
        summary=f"{name} {ip}",
    )
    await session.commit()
    await _regen(session)


@router.post("/{device_id}/rotate-secret", response_model=DeviceRead)
async def rotate_secret(
    device_id: int,
    payload: DeviceRotateSecret,
    ctx: Annotated[SessionContext, Depends(require_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DeviceRead:
    """Shift the current secret into `previous`, set a new `current`.

    Caller is expected to copy the new secret to the device side and then
    call `/retire-previous` once the change is propagated. ADR-0007.
    """
    row = await session.get(Device, device_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    # `current_secret_enc` is already decrypted at load time by the
    # EncryptedStr type; re-assigning re-encrypts on flush. No manual
    # crypto needed here.
    row.previous_secret_enc = row.current_secret_enc
    row.previous_retired_at = None
    row.current_secret_enc = payload.new_secret
    await append_crud(
        session, ctx,
        action=DEVICE_SECRET_ROTATED,
        target_type="device", target_id=row.id,
        summary=row.name,
    )
    await session.commit()
    await session.refresh(row)
    await _regen(session)
    return DeviceRead.from_row(row)


@router.post("/{device_id}/retire-previous", response_model=DeviceRead)
async def retire_previous_secret(
    device_id: int,
    ctx: Annotated[SessionContext, Depends(require_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DeviceRead:
    row = await session.get(Device, device_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    row.previous_secret_enc = None
    row.previous_retired_at = datetime.now(tz=row.updated_at.tzinfo if row.updated_at else None)
    await append_crud(
        session, ctx,
        action=DEVICE_PREVIOUS_RETIRED,
        target_type="device", target_id=row.id,
        summary=row.name,
    )
    await session.commit()
    await session.refresh(row)
    await _regen(session)
    return DeviceRead.from_row(row)
