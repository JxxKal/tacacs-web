"""APScheduler glue for the AD-sync background loop.

Runs inside the FastAPI process. We use AsyncIOScheduler because it
shares the event loop and lifecycle with the rest of the app; each job
firing wraps the sync orchestrator in `asyncio.to_thread` so the sync
DB session / ldap3 bind don't block the loop.

The scheduler reads the configured cadence from `system_setting` on
init and on every cadence-change PUT; calls to `update_cadence()` /
`update_enabled()` from the settings endpoint keep it in sync.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.db.session import SyncSessionLocal
from app.ldap_sync.worker import (
    CADENCE_DEFAULT_SECONDS,
    SyncRunError,
    load_config,
    persist_error_summary,
    run_full_sync,
)

JOB_ID = "ad_sync_loop"

_scheduler: AsyncIOScheduler | None = None
_log = structlog.get_logger("ad_sync.scheduler")
logging.getLogger("apscheduler").setLevel(logging.WARNING)


def start_scheduler() -> None:
    """Wire the periodic job. Idempotent (safe to call from lifespan).

    DB unreachable at boot is NOT fatal — we still want the FastAPI app
    to come up so the operator can fix the DB / config from outside.
    The next `refresh_from_db` call (after a settings PUT, or a manual
    /run) re-tries the lookup.
    """
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = AsyncIOScheduler(timezone="UTC")
    _scheduler.start()
    try:
        refresh_from_db()
    except Exception as exc:
        _log.warning("ad_sync.start_refresh_failed", error=str(exc))


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is None:
        return
    _scheduler.shutdown(wait=False)
    _scheduler = None


def refresh_from_db() -> None:
    """Re-read enabled/cadence from system_setting and reschedule accordingly."""
    if _scheduler is None:
        return
    with SyncSessionLocal() as session:
        cfg = load_config(session)
    cadence = cfg.cadence_seconds if cfg else CADENCE_DEFAULT_SECONDS
    enabled = bool(cfg and cfg.enabled)
    if enabled:
        _scheduler.add_job(
            _tick,
            "interval",
            seconds=cadence,
            id=JOB_ID,
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            next_run_time=datetime.now(UTC),
        )
        _log.info("ad_sync.scheduled", cadence_seconds=cadence)
    else:
        if _scheduler.get_job(JOB_ID) is not None:
            _scheduler.remove_job(JOB_ID)
        _log.info("ad_sync.disabled")


async def trigger_now() -> None:
    """Run a single sync immediately, regardless of cadence.

    Returns once the run completes. Errors propagate so the caller can
    record them in the audit log with the right action code.
    """
    await asyncio.to_thread(_run_once_sync)


async def _tick() -> None:
    """Scheduled-job entry point. Errors are caught + persisted."""
    try:
        await asyncio.to_thread(_run_once_sync)
    except SyncRunError as exc:
        _log.warning("ad_sync.tick_failed", error=str(exc))
        await asyncio.to_thread(persist_error_summary, str(exc))
    except Exception as exc:
        _log.exception("ad_sync.tick_crashed")
        await asyncio.to_thread(persist_error_summary, f"unexpected: {exc!r}")


def _run_once_sync() -> None:
    """Synchronous body run inside `asyncio.to_thread`."""
    with SyncSessionLocal() as session:
        try:
            summary = run_full_sync(session)
        except SyncRunError:
            session.rollback()
            raise
        session.commit()
        _log.info(
            "ad_sync.completed",
            users_seen=summary.users_seen,
            users_inserted=summary.users_inserted,
            users_updated=summary.users_updated,
            users_disabled=summary.users_disabled,
        )
