"""Read-only listings of AD-synced principals.

Users and AD groups are written by the sync worker (M3); the UI only ever
reads them to populate Select inputs in the Authorisation editor. No
create / update / delete here — UI-side principal management is out of
scope for v1 (CONTEXT.md, ADR-0002).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ADGroup, User
from app.db.session import get_session

users_router = APIRouter()
ad_groups_router = APIRouter()


class UserRead(BaseModel):
    id: int
    sam_account_name: str
    distinguished_name: str
    display_name: str | None
    upn: str | None
    enabled: bool
    last_seen_in_sync_at: datetime | None

    model_config = {"from_attributes": True}


class ADGroupRead(BaseModel):
    id: int
    sid: str
    distinguished_name: str
    name: str | None
    last_seen_in_sync_at: datetime | None

    model_config = {"from_attributes": True}


@users_router.get("", response_model=list[UserRead])
async def list_users(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[User]:
    return list(
        (await session.execute(select(User).order_by(User.sam_account_name))).scalars().all()
    )


@ad_groups_router.get("", response_model=list[ADGroupRead])
async def list_ad_groups(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[ADGroup]:
    return list((await session.execute(select(ADGroup).order_by(ADGroup.name))).scalars().all())
