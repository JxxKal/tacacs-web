"""Unit tests for the AD sync core (no real LDAP)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ADGroup, User, UserADGroup
from app.ldap_sync import ADUserRecord, run_sync
from app.ldap_sync.sync import ADGroupRecord


def _record(
    sam: str,
    *,
    dn: str | None = None,
    groups: tuple[ADGroupRecord, ...] = (),
    upn: str | None = None,
) -> ADUserRecord:
    return ADUserRecord(
        sam_account_name=sam,
        distinguished_name=dn or f"CN={sam},OU=People,DC=corp,DC=tld",
        ad_object_guid=None,
        upn=upn or f"{sam}@corp.tld",
        display_name=sam.title(),
        groups=groups,
    )


def test_first_sync_inserts_users_and_groups(db_session: Session) -> None:
    admins = ADGroupRecord(
        sid="S-1-5-21-1-2-3-100",
        distinguished_name="CN=Admins,OU=Groups,DC=corp,DC=tld",
        name="Admins",
    )
    users = [_record("jan", groups=(admins,)), _record("alex", groups=(admins,))]

    result = run_sync(session=db_session, users=users)

    assert result.users_seen == 2
    assert result.users_inserted == 2
    assert result.users_updated == 0
    assert result.users_disabled == 0
    assert result.groups_seen == 1
    assert result.edges_total == 2

    rows = db_session.execute(select(User)).scalars().all()
    assert {u.sam_account_name for u in rows} == {"jan", "alex"}
    assert all(u.enabled for u in rows)

    group_rows = db_session.execute(select(ADGroup)).scalars().all()
    assert {g.sid for g in group_rows} == {admins.sid}


def test_second_sync_updates_existing_user(db_session: Session) -> None:
    run_sync(session=db_session, users=[_record("jan")])
    updated = _record("jan", upn="jan.new@corp.tld")
    result = run_sync(session=db_session, users=[updated])

    assert result.users_inserted == 0
    assert result.users_updated == 1
    user = db_session.execute(select(User).where(User.sam_account_name == "jan")).scalar_one()
    assert user.upn == "jan.new@corp.tld"


def test_missing_user_is_soft_disabled(db_session: Session) -> None:
    run_sync(session=db_session, users=[_record("jan"), _record("alex")])
    result = run_sync(session=db_session, users=[_record("jan")])

    assert result.users_disabled == 1
    alex = db_session.execute(select(User).where(User.sam_account_name == "alex")).scalar_one()
    assert alex.enabled is False


def test_empty_sync_does_not_disable_existing_users(db_session: Session) -> None:
    """Guard against the failure mode where AD returns zero results (transient)
    and we'd otherwise wipe every user's permissions."""
    run_sync(session=db_session, users=[_record("jan"), _record("alex")])
    result = run_sync(session=db_session, users=[])

    assert result.users_disabled == 0
    users = db_session.execute(select(User)).scalars().all()
    assert all(u.enabled for u in users)


def test_group_membership_changes_replace_edges(db_session: Session) -> None:
    g1 = ADGroupRecord(
        sid="S-1-5-21-1-2-3-100",
        distinguished_name="CN=Admins,OU=Groups,DC=corp,DC=tld",
        name="Admins",
    )
    g2 = ADGroupRecord(
        sid="S-1-5-21-1-2-3-101",
        distinguished_name="CN=Operators,OU=Groups,DC=corp,DC=tld",
        name="Operators",
    )

    run_sync(session=db_session, users=[_record("jan", groups=(g1, g2))])
    run_sync(session=db_session, users=[_record("jan", groups=(g2,))])

    jan = db_session.execute(select(User).where(User.sam_account_name == "jan")).scalar_one()
    db_session.refresh(jan)
    sids = {g.sid for g in jan.groups}
    assert sids == {g2.sid}

    edges = (
        db_session.execute(select(UserADGroup).where(UserADGroup.user_id == jan.id)).scalars().all()
    )
    assert len(edges) == 1
