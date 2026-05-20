"""Tail the daemon's accounting log and persist into `accounting_record`.

Wire format we ask the daemon to emit (set in
docker/tac_plus-ng/tac_plus-ng.cfg.template):

    ${time}\\t${nas}\\t${user}\\t${port}\\t${nac}\\t${task_id}\\t${accttype}\\t${args}

8 tab-separated fields per line; the trailing `${args}` is the AV-pair
payload joined by tac_plus-ng's own internal separator. We split it on
both tabs and spaces and pick up `key=value` tokens, handling the common
shell-quoting cases (`cmd="show running-config"`).

Offset tracking: the last-fully-consumed byte offset lives in
`system_setting('accounting.log_offset')`. On restart we resume from
there; if the file shrank under us (truncated or rotated out), we reset
to 0.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import re
import shlex
from datetime import UTC, datetime
from pathlib import Path

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AccountingRecord, Device, SystemSetting
from app.db.session import SessionLocal

ACCT_LOG_PATH = Path(
    os.environ.get("TACACS_WEB_ACCT_LOG", "/var/log/tac_plus-ng/accounting.log")
)
SETTING_OFFSET = "accounting.log_offset"

_TASK: asyncio.Task[None] | None = None
_log = structlog.get_logger("accounting.ingestor")

# Each tac_plus-ng log line tab-separates the 8 top-level fields.
# Fields can be empty (e.g., no nac for a console session) but tabs are
# always emitted. We allow trailing extra tabs / spaces in the args.
_FIELD_COUNT_MIN = 8


def parse_record(line: str) -> dict[str, object] | None:
    """Parse one accounting log line. Returns None on unparseable input."""
    line = line.rstrip("\n").rstrip("\r")
    if not line:
        return None
    parts = line.split("\t")
    if len(parts) < _FIELD_COUNT_MIN:
        return None
    ts_raw, nas, user, port, nac, task_id, action, args_raw = parts[:8]
    extras = parts[8:]
    args_blob = "\t".join([args_raw, *extras]) if extras else args_raw
    return {
        "ts": _parse_ts(ts_raw),
        "nas_ip": nas or None,
        "username": user or None,
        "port": port or None,
        "nac_ip": nac or None,
        "task_id": task_id or None,
        "action": action or "unknown",
        "av_pairs": _parse_args(args_blob),
    }


_AV_TOKEN = re.compile(r"^([A-Za-z0-9._\-]+)=(.*)$")


def _parse_args(blob: str) -> dict[str, str]:
    """Best-effort AV-pair extraction from the tail of the log line.

    tac_plus-ng joins AV pairs with either tabs or spaces depending on
    build; values can be shell-quoted when they contain whitespace
    (`cmd="show run"`). shlex.split handles the quoting correctly.
    """
    out: dict[str, str] = {}
    if not blob:
        return out
    # Normalise tabs to spaces so shlex doesn't get confused.
    blob = blob.replace("\t", " ").strip()
    try:
        tokens = shlex.split(blob)
    except ValueError:
        # Malformed quoting; fall back to whitespace split and accept
        # whatever we can parse.
        tokens = blob.split()
    for tok in tokens:
        m = _AV_TOKEN.match(tok)
        if m:
            out[m.group(1)] = m.group(2)
    return out


def _parse_ts(raw: str) -> datetime:
    """Try a few common tac_plus-ng timestamp formats.

    Default is locale-dependent free-form ("Tue May 20 17:00:00 2026")
    so we accept what we recognise and fall back to now() on failure
    rather than dropping the record entirely.
    """
    raw = raw.strip()
    if not raw:
        return datetime.now(UTC)
    # Pure-integer epoch.
    if raw.isdigit():
        try:
            return datetime.fromtimestamp(int(raw), tz=UTC)
        except (ValueError, OverflowError, OSError):
            pass
    # ISO 8601 with explicit zone.
    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S %z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            dt = datetime.strptime(raw, fmt)
            return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
        except ValueError:
            continue
    # `time(3)` ctime style: "Tue May 20 17:00:00 2026".
    try:
        dt = datetime.strptime(raw, "%a %b %d %H:%M:%S %Y")
        return dt.replace(tzinfo=UTC)
    except ValueError:
        pass
    return datetime.now(UTC)


async def _load_offset(session: AsyncSession) -> int:
    row = (
        await session.execute(
            select(SystemSetting).where(SystemSetting.key == SETTING_OFFSET)
        )
    ).scalar_one_or_none()
    if row is None or not row.value.isdigit():
        return 0
    return int(row.value)


async def _save_offset(session: AsyncSession, offset: int) -> None:
    row = (
        await session.execute(
            select(SystemSetting).where(SystemSetting.key == SETTING_OFFSET)
        )
    ).scalar_one_or_none()
    if row is None:
        session.add(SystemSetting(key=SETTING_OFFSET, value=str(offset)))
    else:
        row.value = str(offset)


async def _resolve_device_id(session: AsyncSession, nas_ip: str | None) -> int | None:
    """Best-effort match: exact ip or contained-in-cidr.

    Falls back to None if no match. Light query so we can do it per row.
    Performance becomes interesting at >>1k accounting records / s; for
    now this is fine for any realistic admin-team workload.
    """
    if not nas_ip:
        return None
    rows = (await session.execute(select(Device))).scalars().all()
    from app.authz.device_resolution import resolve_device_for_ip

    matched = resolve_device_for_ip(nas_ip, rows)
    return matched.id if matched else None


async def _persist_one(session: AsyncSession, rec: dict[str, object]) -> None:
    nas_ip_val = rec["nas_ip"]
    nas_ip = nas_ip_val if isinstance(nas_ip_val, str) else None
    device_id = await _resolve_device_id(session, nas_ip)
    args = rec["av_pairs"] if isinstance(rec["av_pairs"], dict) else {}
    priv_lvl: int | None = None
    if "priv-lvl" in args:
        try:
            priv_lvl = int(args["priv-lvl"])
        except (ValueError, TypeError):
            priv_lvl = None
    elapsed: int | None = None
    if "elapsed_time" in args:
        try:
            elapsed = int(args["elapsed_time"])
        except (ValueError, TypeError):
            elapsed = None
    session.add(
        AccountingRecord(
            ts=rec["ts"],
            nas_ip=nas_ip,
            username=rec["username"],
            port=rec["port"],
            nac_ip=rec["nac_ip"],
            action=rec["action"],
            service=args.get("service"),
            cmd=args.get("cmd"),
            priv_lvl=priv_lvl,
            elapsed_seconds=elapsed,
            task_id=rec["task_id"],
            device_id=device_id,
            raw_av_pairs=args,
        )
    )


async def _tail_loop() -> None:
    """Outer loop: handle file-not-yet-existing and rotation."""
    while True:
        if not ACCT_LOG_PATH.exists():
            await asyncio.sleep(2.0)
            continue
        try:
            await _consume_file(ACCT_LOG_PATH)
        except FileNotFoundError:
            await asyncio.sleep(2.0)
        except asyncio.CancelledError:
            raise
        except Exception:
            _log.exception("accounting.ingestor_crashed")
            await asyncio.sleep(5.0)


async def _consume_file(path: Path) -> None:
    """Read from the file starting at the persisted offset.

    Returns (silently) if the file rotates so the outer loop can reopen.
    """
    async with SessionLocal() as session:
        offset = await _load_offset(session)
        size = path.stat().st_size
        if offset > size:
            offset = 0
            await _save_offset(session, 0)
            await session.commit()

    with path.open("r", encoding="utf-8", errors="replace") as f:
        f.seek(offset)
        while True:
            line = f.readline()
            if line:
                rec = parse_record(line)
                if rec:
                    async with SessionLocal() as session:
                        await _persist_one(session, rec)
                        await _save_offset(session, f.tell())
                        await session.commit()
                continue
            # EOF — flush offset, sleep, then check whether the file
            # rotated. If so, exit so the outer loop reopens.
            current = f.tell()
            try:
                stat = path.stat()
            except FileNotFoundError:
                return
            if stat.st_size < current:
                return  # truncated / rotated
            await asyncio.sleep(1.0)


def start_ingestor() -> None:
    global _TASK
    if _TASK is not None and not _TASK.done():
        return
    _TASK = asyncio.create_task(_tail_loop(), name="accounting-ingestor")
    _log.info("accounting.ingestor_started", path=str(ACCT_LOG_PATH))


async def stop_ingestor() -> None:
    global _TASK
    if _TASK is None:
        return
    _TASK.cancel()
    with contextlib.suppress(asyncio.CancelledError, Exception):
        await _TASK
    _TASK = None
    _log.info("accounting.ingestor_stopped")
