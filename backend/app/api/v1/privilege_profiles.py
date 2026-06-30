"""CRUD for PrivilegeProfile."""

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
    PRIVILEGE_PROFILE_CREATED,
    PRIVILEGE_PROFILE_DELETED,
    PRIVILEGE_PROFILE_UPDATED,
)
from app.auth.sessions import SessionContext, require_session
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
    ctx: Annotated[SessionContext, Depends(require_session)],
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
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail="name_already_exists") from exc
    await append_crud(
        session,
        ctx,
        action=PRIVILEGE_PROFILE_CREATED,
        target_type="privilege_profile",
        target_id=row.id,
        summary=f"{row.name} priv-lvl={row.tacacs_priv_lvl}",
    )
    await session.commit()
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
    ctx: Annotated[SessionContext, Depends(require_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PrivilegeProfile:
    row = await session.get(PrivilegeProfile, profile_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    changed: list[str] = []
    if payload.name is not None and payload.name != row.name:
        changed.append(f"name {row.name!r}->{payload.name!r}")
        row.name = payload.name
    if payload.tacacs_priv_lvl is not None and payload.tacacs_priv_lvl != row.tacacs_priv_lvl:
        changed.append(f"priv-lvl {row.tacacs_priv_lvl}->{payload.tacacs_priv_lvl}")
        row.tacacs_priv_lvl = payload.tacacs_priv_lvl
    if payload.permit_commands_regex is not None:
        changed.append("permit_commands")
        row.permit_commands_regex = payload.permit_commands_regex
    if payload.deny_commands_regex is not None:
        changed.append("deny_commands")
        row.deny_commands_regex = payload.deny_commands_regex
    if payload.extra_av_pairs is not None:
        changed.append("extra_av_pairs")
        row.extra_av_pairs = payload.extra_av_pairs
    if payload.description is not None:
        changed.append("description")
        row.description = payload.description
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail="name_already_exists") from exc
    await append_crud(
        session,
        ctx,
        action=PRIVILEGE_PROFILE_UPDATED,
        target_type="privilege_profile",
        target_id=row.id,
        summary=f"{row.name}: {', '.join(changed) or 'no-op'}",
    )
    await session.commit()
    await session.refresh(row)
    return row


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_privilege_profile(
    profile_id: int,
    ctx: Annotated[SessionContext, Depends(require_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    row = await session.get(PrivilegeProfile, profile_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    name, row_id = row.name, row.id
    await session.delete(row)
    await append_crud(
        session,
        ctx,
        action=PRIVILEGE_PROFILE_DELETED,
        target_type="privilege_profile",
        target_id=row_id,
        summary=name,
    )
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail="profile_in_use") from exc
