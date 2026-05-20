"""CRUD for DeviceGroup."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append_crud
from app.audit.actions import (
    DEVICE_GROUP_CREATED,
    DEVICE_GROUP_DELETED,
    DEVICE_GROUP_UPDATED,
)
from app.auth.sessions import SessionContext, require_session
from app.db.models import DeviceGroup
from app.db.session import get_session

router = APIRouter()


class DeviceGroupCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2048)


class DeviceGroupUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2048)


class DeviceGroupRead(BaseModel):
    id: int
    name: str
    description: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


@router.get("", response_model=list[DeviceGroupRead])
async def list_device_groups(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[DeviceGroup]:
    return list(
        (await session.execute(select(DeviceGroup).order_by(DeviceGroup.id))).scalars().all()
    )


@router.post("", response_model=DeviceGroupRead, status_code=status.HTTP_201_CREATED)
async def create_device_group(
    payload: DeviceGroupCreate,
    ctx: Annotated[SessionContext, Depends(require_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DeviceGroup:
    row = DeviceGroup(name=payload.name, description=payload.description)
    session.add(row)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail="name_already_exists") from exc
    await append_crud(
        session, ctx,
        action=DEVICE_GROUP_CREATED,
        target_type="device_group", target_id=row.id,
        summary=row.name,
    )
    await session.commit()
    await session.refresh(row)
    return row


@router.get("/{device_group_id}", response_model=DeviceGroupRead)
async def get_device_group(
    device_group_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DeviceGroup:
    row = await session.get(DeviceGroup, device_group_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return row


@router.patch("/{device_group_id}", response_model=DeviceGroupRead)
async def update_device_group(
    device_group_id: int,
    payload: DeviceGroupUpdate,
    ctx: Annotated[SessionContext, Depends(require_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DeviceGroup:
    row = await session.get(DeviceGroup, device_group_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    changed: list[str] = []
    if payload.name is not None and payload.name != row.name:
        changed.append(f"name {row.name!r}->{payload.name!r}")
        row.name = payload.name
    if payload.description is not None:
        changed.append("description")
        row.description = payload.description
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail="name_already_exists") from exc
    await append_crud(
        session, ctx,
        action=DEVICE_GROUP_UPDATED,
        target_type="device_group", target_id=row.id,
        summary=f"{row.name}: {', '.join(changed) or 'no-op'}",
    )
    await session.commit()
    await session.refresh(row)
    return row


@router.delete("/{device_group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device_group(
    device_group_id: int,
    ctx: Annotated[SessionContext, Depends(require_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    row = await session.get(DeviceGroup, device_group_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    name, row_id = row.name, row.id
    await session.delete(row)
    await append_crud(
        session, ctx,
        action=DEVICE_GROUP_DELETED,
        target_type="device_group", target_id=row_id,
        summary=name,
    )
    try:
        await session.commit()
    except IntegrityError as exc:
        # FK from device / authorization -> device_group is RESTRICT.
        await session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="device_group_in_use"
        ) from exc
