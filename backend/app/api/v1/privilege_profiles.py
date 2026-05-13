"""CRUD for PrivilegeProfile."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PrivilegeProfile
from app.db.session import get_session

router = APIRouter()


class PrivilegeProfileCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    tacacs_priv_lvl: int = Field(..., ge=0, le=15)
    permit_commands_regex: list[str] = Field(default_factory=list)
    deny_commands_regex: list[str] = Field(default_factory=list)
    extra_av_pairs: dict[str, str] = Field(default_factory=dict)
    description: str | None = Field(default=None, max_length=2048)


class PrivilegeProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    tacacs_priv_lvl: int | None = Field(default=None, ge=0, le=15)
    permit_commands_regex: list[str] | None = None
    deny_commands_regex: list[str] | None = None
    extra_av_pairs: dict[str, str] | None = None
    description: str | None = Field(default=None, max_length=2048)


class PrivilegeProfileRead(BaseModel):
    id: int
    name: str
    tacacs_priv_lvl: int
    permit_commands_regex: list[str]
    deny_commands_regex: list[str]
    extra_av_pairs: dict[str, str]
    description: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


@router.get("", response_model=list[PrivilegeProfileRead])
async def list_privilege_profiles(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[PrivilegeProfile]:
    return list(
        (await session.execute(select(PrivilegeProfile).order_by(PrivilegeProfile.id)))
        .scalars()
        .all()
    )


@router.post("", response_model=PrivilegeProfileRead, status_code=status.HTTP_201_CREATED)
async def create_privilege_profile(
    payload: PrivilegeProfileCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PrivilegeProfile:
    row = PrivilegeProfile(
        name=payload.name,
        tacacs_priv_lvl=payload.tacacs_priv_lvl,
        permit_commands_regex=payload.permit_commands_regex,
        deny_commands_regex=payload.deny_commands_regex,
        extra_av_pairs=payload.extra_av_pairs,
        description=payload.description,
    )
    session.add(row)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail="name_already_exists") from exc
    await session.refresh(row)
    return row


@router.get("/{profile_id}", response_model=PrivilegeProfileRead)
async def get_privilege_profile(
    profile_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PrivilegeProfile:
    row = await session.get(PrivilegeProfile, profile_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return row


@router.patch("/{profile_id}", response_model=PrivilegeProfileRead)
async def update_privilege_profile(
    profile_id: int,
    payload: PrivilegeProfileUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PrivilegeProfile:
    row = await session.get(PrivilegeProfile, profile_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    if payload.name is not None:
        row.name = payload.name
    if payload.tacacs_priv_lvl is not None:
        row.tacacs_priv_lvl = payload.tacacs_priv_lvl
    if payload.permit_commands_regex is not None:
        row.permit_commands_regex = payload.permit_commands_regex
    if payload.deny_commands_regex is not None:
        row.deny_commands_regex = payload.deny_commands_regex
    if payload.extra_av_pairs is not None:
        row.extra_av_pairs = payload.extra_av_pairs
    if payload.description is not None:
        row.description = payload.description
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail="name_already_exists") from exc
    await session.refresh(row)
    return row


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_privilege_profile(
    profile_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    row = await session.get(PrivilegeProfile, profile_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    await session.delete(row)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="profile_in_use"
        ) from exc
