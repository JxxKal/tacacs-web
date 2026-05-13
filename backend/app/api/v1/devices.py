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

from app.db.models import Device, DeviceGroup
from app.db.session import get_session

router = APIRouter()


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
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="name_or_ip_already_exists"
        ) from exc
    await session.refresh(row)
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
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DeviceRead:
    row = await session.get(Device, device_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    if payload.device_group_id is not None:
        await _ensure_device_group_exists(session, payload.device_group_id)
        row.device_group_id = payload.device_group_id
    if payload.name is not None:
        row.name = payload.name
    if payload.ip_or_cidr is not None:
        row.ip_or_cidr = payload.ip_or_cidr
    if payload.description is not None:
        row.description = payload.description
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="name_or_ip_already_exists"
        ) from exc
    await session.refresh(row)
    return DeviceRead.from_row(row)


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device(
    device_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    row = await session.get(Device, device_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    await session.delete(row)
    await session.commit()


@router.post("/{device_id}/rotate-secret", response_model=DeviceRead)
async def rotate_secret(
    device_id: int,
    payload: DeviceRotateSecret,
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
    await session.commit()
    await session.refresh(row)
    return DeviceRead.from_row(row)


@router.post("/{device_id}/retire-previous", response_model=DeviceRead)
async def retire_previous_secret(
    device_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DeviceRead:
    row = await session.get(Device, device_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    row.previous_secret_enc = None
    row.previous_retired_at = datetime.now(tz=row.updated_at.tzinfo if row.updated_at else None)
    await session.commit()
    await session.refresh(row)
    return DeviceRead.from_row(row)
