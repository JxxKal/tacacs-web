"""Compute the effective PrivilegeProfile for a (user, device_group) pair.

ADR-0006 ground rules:
- Authorizations from many sources stack permissively: highest `priv_lvl` wins.
- A direct-user Authorization beats any AD-group Authorization, regardless of
  priv-lvl. This is the "personal override" carve-out.
- Tie-breaks (same priv-lvl, different profiles) are deterministic by
  Authorization row id, but treated as effectively interchangeable. The UI
  (`/api/v1/users/{id}/effective-permissions`) surfaces the ambiguity to the
  operator.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.db.models import Authorization, PrivilegeProfile, User


@dataclass(frozen=True)
class EffectiveAuthorization:
    """Outcome of evaluating one (user, device_group) authorisation question.

    `winning` is None iff the user has zero matching authorizations on the
    device_group (treated as "no access" by the caller). `overridden` is the
    list of candidates that lost to the winner; useful for the
    effective-permissions UI.
    """

    winning: Authorization | None
    overridden: tuple[Authorization, ...]

    @property
    def profile(self) -> PrivilegeProfile | None:
        return self.winning.privilege_profile if self.winning else None


def evaluate_for_user(
    user: User,
    device_group_id: int,
    authorizations: Iterable[Authorization],
) -> EffectiveAuthorization:
    """Pick the winning Authorization for `user` on `device_group_id`.

    `authorizations` is the unfiltered set the caller has in hand (typically
    every Authorization joined with the matching DeviceGroup); we filter and
    score here so the SQL stays naive.
    """
    user_group_ids = {g.id for g in user.groups}

    candidates: list[Authorization] = []
    for auth in authorizations:
        if auth.device_group_id != device_group_id:
            continue
        if auth.principal_user_id == user.id:
            candidates.append(auth)
            continue
        if (
            auth.principal_ad_group_id is not None
            and auth.principal_ad_group_id in user_group_ids
        ):
            candidates.append(auth)

    if not candidates:
        return EffectiveAuthorization(winning=None, overridden=())

    direct = [c for c in candidates if c.is_direct]
    pool = direct if direct else candidates

    pool.sort(
        key=lambda a: (-a.privilege_profile.tacacs_priv_lvl, a.id),
    )
    winner = pool[0]
    overridden = tuple(c for c in candidates if c is not winner)
    return EffectiveAuthorization(winning=winner, overridden=overridden)
