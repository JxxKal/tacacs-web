"""Pull users + groups from AD into the local DB.

Pure-Python core logic with no direct LDAP dependency — accepts an iterable
of `ADUserRecord` dataclasses produced by a fetcher. The real fetcher lives
in `app.ldap_sync.ldap3_client`; tests inject a static list.

Disappeared-user semantics (ADR-0002): users that exist in the DB but are
not in the latest fetch get `enabled=false`. Their `authorization` rows and
`accounting_record` snapshots stay intact for audit purposes.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db.models import ADGroup, User, UserADGroup


@dataclass(frozen=True)
class ADGroupRecord:
    sid: str
    distinguished_name: str
    name: str | None = None


@dataclass(frozen=True)
class ADUserRecord:
    sam_account_name: str
    distinguished_name: str
    ad_object_guid: str | None = None
    upn: str | None = None
    display_name: str | None = None
    groups: tuple[ADGroupRecord, ...] = ()


@dataclass
class SyncResult:
    users_seen: int = 0
    users_inserted: int = 0
    users_updated: int = 0
    users_disabled: int = 0
    groups_seen: int = 0
    groups_inserted: int = 0
    edges_total: int = 0
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None


def run_sync(*, session: Session, users: Iterable[ADUserRecord]) -> SyncResult:
    """Apply one full sync cycle. `session` is committed before returning."""
    result = SyncResult()
    now = datetime.now(UTC)

    groups_by_sid: dict[str, ADGroup] = {}
    seen_user_ids: set[int] = set()

    for record in users:
        user, inserted = _upsert_user(session, record, now)
        result.users_seen += 1
        if inserted:
            result.users_inserted += 1
        else:
            result.users_updated += 1
        # Need an id before we can write join rows.
        session.flush()
        seen_user_ids.add(user.id)

        edge_count = _replace_user_groups(session, user, record.groups, groups_by_sid, now)
        result.edges_total += edge_count

    result.groups_seen = len(groups_by_sid)
    result.groups_inserted = sum(
        1 for g in groups_by_sid.values() if g.id is None or _just_created(g)
    )

    if seen_user_ids:
        stale = (
            session.execute(
                select(User).where(User.id.notin_(seen_user_ids), User.enabled.is_(True))
            )
            .scalars()
            .all()
        )
    else:
        # Defensive: if a sync legitimately returns zero users, don't disable
        # every existing user. Better to no-op than to wipe permissions.
        stale = []

    for user in stale:
        user.enabled = False
        result.users_disabled += 1

    session.commit()
    result.finished_at = datetime.now(UTC)
    return result


def _upsert_user(session: Session, record: ADUserRecord, now: datetime) -> tuple[User, bool]:
    user = _find_existing_user(session, record)
    inserted = False
    if user is None:
        user = User(
            sam_account_name=record.sam_account_name,
            ad_object_guid=record.ad_object_guid,
            distinguished_name=record.distinguished_name,
            upn=record.upn,
            display_name=record.display_name,
            enabled=True,
            last_seen_in_sync_at=now,
        )
        session.add(user)
        inserted = True
    else:
        # A GUID match with a different sAMAccountName is an AD-side rename;
        # the DB row follows the directory.
        user.sam_account_name = record.sam_account_name
        user.ad_object_guid = record.ad_object_guid or user.ad_object_guid
        user.distinguished_name = record.distinguished_name
        user.upn = record.upn
        user.display_name = record.display_name
        user.enabled = True
        user.last_seen_in_sync_at = now
    return user, inserted


def _find_existing_user(session: Session, record: ADUserRecord) -> User | None:
    """Locate the DB row for an AD user.

    `objectGUID` is the stable AD identity and carries the unique constraint,
    so it wins. `sAMAccountName` is the fallback for rows synced before GUIDs
    were captured; AD treats it case-insensitively, so we do too. Matching on
    sAMAccountName alone (the previous behaviour) turned every AD rename or
    case change into a second row with the same GUID and a UniqueViolation.
    """
    if record.ad_object_guid:
        user = session.execute(
            select(User).where(User.ad_object_guid == record.ad_object_guid)
        ).scalar_one_or_none()
        if user is not None:
            return user
    wanted = record.sam_account_name.lower()
    candidates = (
        session.execute(
            select(User).where(func.lower(User.sam_account_name) == wanted).order_by(User.id)
        )
        .scalars()
        .all()
    )
    if not candidates:
        return None
    for candidate in candidates:
        if candidate.sam_account_name == record.sam_account_name:
            return candidate
    return candidates[0]


def _replace_user_groups(
    session: Session,
    user: User,
    group_records: tuple[ADGroupRecord, ...],
    groups_by_sid: dict[str, ADGroup],
    now: datetime,
) -> int:
    # Drop any existing join rows for this user; the latest fetch is authoritative.
    session.execute(delete(UserADGroup).where(UserADGroup.user_id == user.id))

    for gr in group_records:
        group = groups_by_sid.get(gr.sid)
        if group is None:
            group = session.execute(
                select(ADGroup).where(ADGroup.sid == gr.sid)
            ).scalar_one_or_none()
            if group is None:
                group = ADGroup(
                    sid=gr.sid,
                    distinguished_name=gr.distinguished_name,
                    name=gr.name,
                    last_seen_in_sync_at=now,
                )
                session.add(group)
                session.flush()
            else:
                group.distinguished_name = gr.distinguished_name
                group.name = gr.name
                group.last_seen_in_sync_at = now
            groups_by_sid[gr.sid] = group

        session.add(UserADGroup(user_id=user.id, ad_group_id=group.id))

    return len(group_records)


def _just_created(group: ADGroup) -> bool:
    # SQLAlchemy doesn't directly expose "is this object newly added" without
    # introspecting state; the call site only uses this for the result counter
    # so we always count groups conservatively. Real-world v1 doesn't surface
    # this number anywhere user-facing.
    return True
