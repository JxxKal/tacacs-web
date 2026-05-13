"""CRUD for DeviceGroup."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

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
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DeviceGroup:
    row = DeviceGroup(name=payload.name, description=payload.description)
    session.add(row)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail="name_already_exists") from exc
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
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DeviceGroup:
    row = await session.get(DeviceGroup, device_group_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    if payload.name is not None:
        row.name = payload.name
    if payload.description is not None:
        row.description = payload.description
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail="name_already_exists") from exc
    await session.refresh(row)
    return row


@router.delete("/{device_group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device_group(
    device_group_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    row = await session.get(DeviceGroup, device_group_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    await session.delete(row)
    try:
        await session.commit()
    except IntegrityError as exc:
        # FK from device / authorization -> device_group is RESTRICT.
        await session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="device_group_in_use"
        ) from exc
