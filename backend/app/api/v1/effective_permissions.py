"""Read-only "Effective Permissions per User" view.

Per ADR-0006 this is the transparency tool: for each DeviceGroup the user
can reach, surface the winning Authorization plus the candidates that
lost. Operators use this to answer "why does Jan have admin?" without
mental simulation.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.sessions import SessionContext, require_session
from app.authz import evaluate_for_user
from app.db.models import Authorization, Device, DeviceGroup, PrivilegeProfile, User
from app.db.session import get_session

router = APIRouter()

# Cap the per-DG device preview to keep the dashboard payload bounded
# even on a 10k-device fleet — operators just need a sample to recognise
# the group, not the full inventory.
MY_ACCESS_DEVICE_PREVIEW = 50


class _CandidateRead(BaseModel):
    authorization_id: int
    principal_user_id: int | None
    principal_ad_group_id: int | None
    privilege_profile_id: int
    tacacs_priv_lvl: int


class EffectivePermissionRead(BaseModel):
    device_group_id: int
    device_group_name: str
    winning: _CandidateRead
    overridden: list[_CandidateRead]


def _to_candidate(a: Authorization) -> _CandidateRead:
    return _CandidateRead(
        authorization_id=a.id,
        principal_user_id=a.principal_user_id,
        principal_ad_group_id=a.principal_ad_group_id,
        privilege_profile_id=a.privilege_profile_id,
        tacacs_priv_lvl=a.privilege_profile.tacacs_priv_lvl,
    )


@router.get(
    "/users/{user_id}/effective-permissions",
    response_model=list[EffectivePermissionRead],
)
async def list_effective_permissions(
    user_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[EffectivePermissionRead]:
    user = (
        await session.execute(
            select(User).options(selectinload(User.groups)).where(User.id == user_id)
        )
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="unknown_user_id")

    group_ids = {g.id for g in user.groups}

    # Pull every authz that *could* match this user (direct + via AD groups),
    # then group by device_group_id and evaluate. Keeps the SQL flat; the
    # join through PrivilegeProfile is eager so the policy can read priv_lvl
    # without lazy-loading.
    candidate_stmt = select(Authorization).where(
        (Authorization.principal_user_id == user_id)
        | (Authorization.principal_ad_group_id.in_(group_ids))
    )
    candidates = list((await session.execute(candidate_stmt)).scalars().all())

    by_dg: dict[int, list[Authorization]] = {}
    for auth in candidates:
        by_dg.setdefault(auth.device_group_id, []).append(auth)

    dgs = {
        dg.id: dg
        for dg in (await session.execute(select(DeviceGroup))).scalars().all()
    }

    out: list[EffectivePermissionRead] = []
    for dg_id, dg_candidates in by_dg.items():
        outcome = evaluate_for_user(user, dg_id, dg_candidates)
        if outcome.winning is None:
            continue
        out.append(
            EffectivePermissionRead(
                device_group_id=dg_id,
                device_group_name=dgs[dg_id].name if dg_id in dgs else "",
                winning=_to_candidate(outcome.winning),
                overridden=[_to_candidate(c) for c in outcome.overridden],
            )
        )
    out.sort(key=lambda e: e.device_group_id)
    return out


class _DeviceRead(BaseModel):
    id: int
    name: str
    ip_or_cidr: str


class MyAccessGroupRead(BaseModel):
    device_group_id: int
    device_group_name: str
    tacacs_priv_lvl: int
    privilege_profile_name: str
    via_ad_group_name: str | None
    devices: list[_DeviceRead]
    device_count: int


class MyAccessRead(BaseModel):
    tacacs_username: str | None
    display_name: str | None
    groups: list[MyAccessGroupRead]


@router.get("/me/access", response_model=MyAccessRead)
async def my_access(
    ctx: Annotated[SessionContext, Depends(require_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> MyAccessRead:
    """Return the calling user's effective TACACS access summary.

    Resolution order: SessionContext.username matched against
    `User.sam_account_name` first (case-insensitive), then `User.upn`.
    For a break-glass local admin we never find a row — the response
    returns an empty `groups` list with `tacacs_username=None` so the
    UI can render the "you don't log in via TACACS" hint instead of an
    error.
    """
    username = (ctx.username or "").strip()
    user: User | None = None
    if username:
        user = (
            await session.execute(
                select(User)
                .options(selectinload(User.groups))
                .where(User.sam_account_name.ilike(username))
            )
        ).scalar_one_or_none()
        if user is None and "@" in username:
            user = (
                await session.execute(
                    select(User)
                    .options(selectinload(User.groups))
                    .where(User.upn.ilike(username))
                )
            ).scalar_one_or_none()

    if user is None:
        return MyAccessRead(tacacs_username=None, display_name=None, groups=[])

    group_ids = {g.id for g in user.groups}
    group_names_by_id = {g.id: g.name for g in user.groups}
    candidate_stmt = (
        select(Authorization)
        .options(selectinload(Authorization.privilege_profile))
        .where(
            (Authorization.principal_user_id == user.id)
            | (Authorization.principal_ad_group_id.in_(group_ids))
        )
    )
    candidates = list((await session.execute(candidate_stmt)).scalars().all())

    by_dg: dict[int, list[Authorization]] = {}
    for auth in candidates:
        by_dg.setdefault(auth.device_group_id, []).append(auth)

    dgs = {
        dg.id: dg
        for dg in (await session.execute(select(DeviceGroup))).scalars().all()
    }
    profiles = {
        pp.id: pp
        for pp in (
            await session.execute(select(PrivilegeProfile))
        ).scalars().all()
    }

    out: list[MyAccessGroupRead] = []
    for dg_id, dg_candidates in by_dg.items():
        outcome = evaluate_for_user(user, dg_id, dg_candidates)
        winner = outcome.winning
        if winner is None:
            continue
        prof = profiles.get(winner.privilege_profile_id)
        devices = (
            await session.execute(
                select(Device)
                .where(Device.device_group_id == dg_id)
                .order_by(Device.name)
            )
        ).scalars().all()
        previews = [
            _DeviceRead(id=d.id, name=d.name, ip_or_cidr=d.ip_or_cidr)
            for d in devices[:MY_ACCESS_DEVICE_PREVIEW]
        ]
        via_group: str | None = None
        if winner.principal_user_id != user.id:
            via_group = group_names_by_id.get(winner.principal_ad_group_id or -1)
        out.append(
            MyAccessGroupRead(
                device_group_id=dg_id,
                device_group_name=dgs[dg_id].name if dg_id in dgs else "",
                tacacs_priv_lvl=prof.tacacs_priv_lvl if prof is not None else -1,
                privilege_profile_name=prof.name if prof is not None else "",
                via_ad_group_name=via_group,
                devices=previews,
                device_count=len(devices),
            )
        )
    out.sort(key=lambda g: g.device_group_name)
    return MyAccessRead(
        tacacs_username=user.sam_account_name,
        display_name=user.display_name,
        groups=out,
    )
