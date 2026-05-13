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

from app.authz import evaluate_for_user
from app.db.models import Authorization, DeviceGroup, User
from app.db.session import get_session

router = APIRouter()


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
