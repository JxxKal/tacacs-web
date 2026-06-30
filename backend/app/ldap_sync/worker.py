"""Glue between the LDAP fetcher and the pure-Python sync engine.

The fetcher (`fetch_users`) and the sync (`run_sync`) are both sync
APIs because ldap3 + the SQLAlchemy ORM helpers we lean on for upsert
are synchronous. This module wraps them in an orchestrator that:

- opens an LDAPS service-account bind from the stored config,
- runs a paged subtree search with the configured user filter,
- applies the result against the DB through a fresh sync session,
- persists the result summary back into `system_setting` so the UI can
  render last-run state without a separate table.

Errors at any stage produce a `SyncRunError` with a human-readable
message that the API surfaces verbatim into audit-log summaries.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from ldap3 import Connection, Server
from ldap3.core.exceptions import LDAPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.ldap_bind import LDAPEndpoint
from app.db.models import SystemSecret, SystemSetting
from app.db.session import SyncSessionLocal
from app.ldap_sync.ldap3_client import DEFAULT_USER_FILTER, fetch_users
from app.ldap_sync.sync import SyncResult, run_sync

SETTING_LDAP_URL = "ldap.url"
SETTING_BIND_DN = "ldap.bind_dn"
SETTING_BASE_DNS = "ldap.base_dns"  # JSON list of strings
SETTING_USER_FILTER = "ldap.user_filter"  # optional override
SETTING_CADENCE = "ldap.sync_cadence_seconds"
SETTING_ENABLED = "ldap.sync_enabled"  # "true" / "false"
SETTING_LAST_RESULT = "ldap.last_sync_result"  # JSON
SECRET_BIND_PASSWORD = "ldap.bind_password"

CADENCE_DEFAULT_SECONDS = 3600
CADENCE_MIN_SECONDS = 60


class SyncRunError(RuntimeError):
    """Raised when a sync attempt cannot complete; carries a UI-safe message."""


@dataclass(frozen=True)
class LdapSyncConfig:
    url: str
    bind_dn: str
    base_dns: tuple[str, ...]
    user_filter: str
    cadence_seconds: int
    enabled: bool


@dataclass
class LdapSyncRunSummary:
    """Last-run snapshot persisted into system_setting for the UI."""

    started_at: str
    finished_at: str | None
    users_seen: int = 0
    users_inserted: int = 0
    users_updated: int = 0
    users_disabled: int = 0
    groups_seen: int = 0
    error: str | None = None

    @classmethod
    def from_sync_result(cls, result: SyncResult) -> LdapSyncRunSummary:
        return cls(
            started_at=result.started_at.isoformat(),
            finished_at=result.finished_at.isoformat() if result.finished_at else None,
            users_seen=result.users_seen,
            users_inserted=result.users_inserted,
            users_updated=result.users_updated,
            users_disabled=result.users_disabled,
            groups_seen=result.groups_seen,
        )


def load_config(session: Session) -> LdapSyncConfig | None:
    """Read the persisted sync config. Returns None if any required field is missing."""
    url = _read_setting(session, SETTING_LDAP_URL)
    bind_dn = _read_setting(session, SETTING_BIND_DN)
    base_dns_raw = _read_setting(session, SETTING_BASE_DNS)
    if not (url and bind_dn and base_dns_raw):
        return None
    try:
        base_dns = tuple(entry for entry in json.loads(base_dns_raw) if isinstance(entry, str))
    except json.JSONDecodeError:
        return None
    if not base_dns:
        return None
    user_filter = _read_setting(session, SETTING_USER_FILTER) or DEFAULT_USER_FILTER
    cadence_str = _read_setting(session, SETTING_CADENCE) or str(CADENCE_DEFAULT_SECONDS)
    try:
        cadence = max(CADENCE_MIN_SECONDS, int(cadence_str))
    except ValueError:
        cadence = CADENCE_DEFAULT_SECONDS
    enabled = (_read_setting(session, SETTING_ENABLED) or "false").lower() == "true"
    return LdapSyncConfig(
        url=url,
        bind_dn=bind_dn,
        base_dns=base_dns,
        user_filter=user_filter,
        cadence_seconds=cadence,
        enabled=enabled,
    )


def load_bind_password(session: Session) -> str | None:
    row = (
        session.execute(select(SystemSecret).where(SystemSecret.key == SECRET_BIND_PASSWORD))
    ).scalar_one_or_none()
    return row.value if row is not None else None


def test_connection(
    url: str,
    bind_dn: str,
    bind_password: str,
    *,
    timeout_s: int = 5,
) -> None:
    """Open one LDAPS bind and immediately tear it down. Raises SyncRunError on failure."""
    server = Server(url, use_ssl=url.lower().startswith("ldaps://"), connect_timeout=timeout_s)
    try:
        conn = Connection(
            server,
            user=bind_dn,
            password=bind_password,
            auto_bind=True,
            receive_timeout=timeout_s,
        )
    except LDAPException as exc:
        raise SyncRunError(f"LDAP bind failed: {exc}") from exc
    try:
        if not conn.bound:
            raise SyncRunError(f"LDAP bind returned not-bound: {conn.result}")
    finally:
        conn.unbind()


def run_full_sync(session: Session, *, now: datetime | None = None) -> LdapSyncRunSummary:
    """End-to-end: fetch + persist. Caller passes a sync session for the persist half.

    Reads config + bind password from the same session before opening the
    LDAP connection. Returns the run-summary that's also written to
    `system_setting` for the UI.
    """
    started = now or datetime.now(UTC)
    cfg = load_config(session)
    if cfg is None:
        raise SyncRunError("LDAP sync is not configured")
    password = load_bind_password(session)
    if password is None:
        raise SyncRunError("LDAP bind password is not set")

    endpoint = LDAPEndpoint(
        url=cfg.url,
        use_tls=cfg.url.lower().startswith("ldaps://"),
        receive_timeout=15,
    )
    server = Server(endpoint.url, use_ssl=endpoint.use_tls, connect_timeout=15)
    try:
        conn = Connection(
            server,
            user=cfg.bind_dn,
            password=password,
            auto_bind=True,
            receive_timeout=30,
        )
    except LDAPException as exc:
        raise SyncRunError(f"LDAP bind failed: {exc}") from exc
    try:
        records = fetch_users(conn, cfg.base_dns, user_filter=cfg.user_filter)
    except LDAPException as exc:
        raise SyncRunError(f"LDAP search failed: {exc}") from exc
    finally:
        conn.unbind()

    result = run_sync(session=session, users=records)
    summary = LdapSyncRunSummary.from_sync_result(result)
    summary.started_at = started.isoformat()
    _persist_summary(session, summary)
    return summary


def persist_error_summary(error: str, *, started: datetime | None = None) -> None:
    """Write a failure marker so the UI sees something other than a stale OK."""
    with SyncSessionLocal() as session:
        summary = LdapSyncRunSummary(
            started_at=(started or datetime.now(UTC)).isoformat(),
            finished_at=datetime.now(UTC).isoformat(),
            error=error,
        )
        _persist_summary(session, summary)
        session.commit()


def _persist_summary(session: Session, summary: LdapSyncRunSummary) -> None:
    payload = json.dumps(asdict(summary))
    row = (
        session.execute(select(SystemSetting).where(SystemSetting.key == SETTING_LAST_RESULT))
    ).scalar_one_or_none()
    if row is None:
        session.add(SystemSetting(key=SETTING_LAST_RESULT, value=payload))
    else:
        row.value = payload


def _read_setting(session: Session, key: str) -> str | None:
    row = (
        session.execute(select(SystemSetting).where(SystemSetting.key == key))
    ).scalar_one_or_none()
    return row.value if row is not None else None
