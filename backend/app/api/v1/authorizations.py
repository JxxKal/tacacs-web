"""CRUD for Authorization edges.

An Authorization row binds exactly one principal (User OR ADGroup) to a
DeviceGroup + PrivilegeProfile. The API enforces "exactly one principal"
both in pydantic (model_validator) and in the DB (CHECK constraint).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append_crud
from app.audit.actions import AUTHORIZATION_CREATED, AUTHORIZATION_DELETED
from app.auth.sessions import SessionContext, require_session
from app.db.models import (
    ADGroup,
    Authorization,
    DeviceGroup,
    PrivilegeProfile,
    User,
)
from app.db.session import get_session

router = APIRouter()


class AuthorizationCreate(BaseModel):
    principal_user_id: int | None = None
    principal_ad_group_id: int | None = None
    device_group_id: int
    privilege_profile_id: int

    @model_validator(mode="after")
    def _exactly_one_principal(self) -> AuthorizationCreate:
        if (self.principal_user_id is None) == (self.principal_ad_group_id is None):
            raise ValueError(
                "exactly one of principal_user_id or principal_ad_group_id must be set"
            )
        return self


class AuthorizationRead(BaseModel):
    id: int
    principal_user_id: int | None
    principal_ad_group_id: int | None
    device_group_id: int
    privilege_profile_id: int
    created_at: datetime

    model_config = {"from_attributes": True}


@router.get("", response_model=list[AuthorizationRead])
async def list_authorizations(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[Authorization]:
    return list(
        (await session.execute(select(Authorization).order_by(Authorization.id))).scalars().all()
    )


@router.post("", response_model=AuthorizationRead, status_code=status.HTTP_201_CREATED)
async def create_authorization(
    payload: AuthorizationCreate,
    ctx: Annotated[SessionContext, Depends(require_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Authorization:
    if payload.principal_user_id is not None:
        if await session.get(User, payload.principal_user_id) is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="unknown_user_id")
    else:
        if await session.get(ADGroup, payload.principal_ad_group_id) is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="unknown_ad_group_id")
    if await session.get(DeviceGroup, payload.device_group_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="unknown_device_group_id")
    if await session.get(PrivilegeProfile, payload.privilege_profile_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="unknown_privilege_profile_id")

    row = Authorization(
        principal_user_id=payload.principal_user_id,
        principal_ad_group_id=payload.principal_ad_group_id,
        device_group_id=payload.device_group_id,
        privilege_profile_id=payload.privilege_profile_id,
    )
    session.add(row)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="authorization_already_exists"
        ) from exc
    principal_desc = (
        f"user#{payload.principal_user_id}"
        if payload.principal_user_id is not None
        else f"ad_group#{payload.principal_ad_group_id}"
    )
    await append_crud(
        session,
        ctx,
        action=AUTHORIZATION_CREATED,
        target_type="authorization",
        target_id=row.id,
        summary=(
            f"{principal_desc} -> dg#{payload.device_group_id} "
            f"profile#{payload.privilege_profile_id}"
        ),
    )
    await session.commit()
    await session.refresh(row)
    return row


@router.get("/{authz_id}", response_model=AuthorizationRead)
async def get_authorization(
    authz_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Authorization:
    row = await session.get(Authorization, authz_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return row


@router.delete("/{authz_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_authorization(
    authz_id: int,
    ctx: Annotated[SessionContext, Depends(require_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    row = await session.get(Authorization, authz_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    principal_desc = (
        f"user#{row.principal_user_id}"
        if row.principal_user_id is not None
        else f"ad_group#{row.principal_ad_group_id}"
    )
    summary = f"{principal_desc} -> dg#{row.device_group_id} profile#{row.privilege_profile_id}"
    row_id = row.id
    await session.delete(row)
    await append_crud(
        session,
        ctx,
        action=AUTHORIZATION_DELETED,
        target_type="authorization",
        target_id=row_id,
        summary=summary,
    )
    await session.commit()
