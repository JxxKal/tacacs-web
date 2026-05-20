"""TCP / TLS RFC5424 + RFC6587 syslog forwarder for accounting records.

Loop semantics:
1. Sleep until something new lands (poll every N seconds; cheap because
   we only query if syslog is enabled).
2. Open one connection per batch (avoid keeping a long-lived socket;
   collectors are tolerant of reconnect-per-batch and this dodges
   keepalive edge cases without an out-of-band heartbeat).
3. Send each row as an RFC6587 octet-counted RFC5424 message.
4. After all rows in the batch are ack'd at TCP level, persist the
   new last-forwarded id atomically — duplicates on retry are
   preferable to loss.

Errors at the connection or write layer cause the batch to fail; the
offset isn't advanced and the next loop tick retries from the same
spot. The Settings card surfaces the last-error reason so operators
can debug without `docker logs`.
"""

from __future__ import annotations

import asyncio
import contextlib
import socket
import ssl
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AccountingRecord, AuditLog, SystemSecret, SystemSetting
from app.db.session import SessionLocal

if TYPE_CHECKING:
    pass

SETTING_ENABLED = "syslog.enabled"
SETTING_HOST = "syslog.host"
SETTING_PORT = "syslog.port"
SETTING_PROTOCOL = "syslog.protocol"  # "tcp" | "tls"
SETTING_FACILITY = "syslog.facility"  # int 0..23 (local0=16)
SETTING_APP_NAME = "syslog.app_name"
SETTING_HOSTNAME = "syslog.hostname"
SETTING_TLS_VERIFY = "syslog.tls_verify"
SETTING_TLS_SERVER_NAME = "syslog.tls_server_name"
SETTING_LAST_ID = "syslog.last_forwarded_id"
SETTING_LAST_AUDIT_ID = "syslog.last_audit_id"
SETTING_LAST_ERROR = "syslog.last_error"
SETTING_LAST_ERROR_AT = "syslog.last_error_at"

# Audit actions that lift the syslog severity from Info to Warning so
# SIEMs can route them differently. Anything *.failed plus the lock-out
# tail-events from auth.* — operators care about failed logins on the
# SIEM, not "user successfully read the device list".
_WARNING_ACTIONS = frozenset(
    {
        "auth.login_failed",
        "auth.session_expired",
        "tacacs.authn_failed",
        "tacacs.authz_failed",
        "ldap_sync.test_failed",
        "ldap_sync.run_failed",
        "syslog.test_failed",
    }
)
SEVERITY_WARNING = 4

SECRET_TLS_CA_PEM = "syslog.tls_ca_pem"
SECRET_TLS_CLIENT_CERT_PEM = "syslog.tls_client_cert_pem"
SECRET_TLS_CLIENT_KEY_PEM = "syslog.tls_client_key_pem"

# Default poll interval. Short enough that operators see new commands
# in their SIEM quickly; long enough that an idle stack doesn't hammer
# the DB.
POLL_SECONDS = 5.0
BATCH_SIZE = 200
SOCKET_TIMEOUT = 10.0

# RFC5424 severity Info; facility default local0 (16).
DEFAULT_FACILITY = 16
SEVERITY_INFO = 6

_log = structlog.get_logger("syslog.forwarder")
_TASK: asyncio.Task[None] | None = None


@dataclass(frozen=True)
class SyslogConfig:
    enabled: bool
    host: str
    port: int
    protocol: str  # "tcp" | "tls"
    facility: int
    app_name: str
    hostname: str
    tls_verify: bool
    tls_server_name: str | None
    tls_ca_pem: str | None
    tls_client_cert_pem: str | None
    tls_client_key_pem: str | None


# --- formatting -----------------------------------------------------------


_SD_NILVALUE = "-"


def _sd_escape(value: str) -> str:
    """RFC5424 PARAM-VALUE escaping for SD-PARAM strings."""
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("]", "\\]")


def _sd_param(name: str, value: str) -> str:
    return f'{name}="{_sd_escape(value)}"'


def format_rfc5424(record: AccountingRecord, cfg: SyslogConfig) -> str:
    """Render one accounting record as an RFC5424 line (no framing)."""
    pri = cfg.facility * 8 + SEVERITY_INFO
    # RFC5424 TIMESTAMP: ISO-8601 with TZ, millisecond precision.
    ts = (
        record.ts.replace(tzinfo=UTC)
        if record.ts.tzinfo is None
        else record.ts.astimezone(UTC)
    )
    timestamp = ts.strftime("%Y-%m-%dT%H:%M:%S.") + f"{ts.microsecond // 1000:03d}Z"

    sd_parts: list[str] = []
    sd_parts.append(_sd_param("action", record.action))
    if record.username:
        sd_parts.append(_sd_param("user", record.username))
    if record.nas_ip:
        sd_parts.append(_sd_param("nas", record.nas_ip))
    if record.nac_ip:
        sd_parts.append(_sd_param("nac", record.nac_ip))
    if record.port:
        sd_parts.append(_sd_param("port", record.port))
    if record.service:
        sd_parts.append(_sd_param("service", record.service))
    if record.cmd:
        sd_parts.append(_sd_param("cmd", record.cmd))
    if record.priv_lvl is not None:
        sd_parts.append(_sd_param("privlvl", str(record.priv_lvl)))
    if record.elapsed_seconds is not None:
        sd_parts.append(_sd_param("elapsed", str(record.elapsed_seconds)))
    if record.task_id:
        sd_parts.append(_sd_param("task", record.task_id))
    sd = "[acct@tacacs-web " + " ".join(sd_parts) + "]"

    # Human-readable MSG body. Cmd if present, else fall back to action.
    msg = record.cmd or f"action={record.action}"
    if record.username:
        msg = f"{record.username}: {msg}"

    header = f"<{pri}>1 {timestamp} {cfg.hostname} {cfg.app_name} - acct"
    return f"{header} {sd} {msg}"


def format_rfc5424_audit(row: AuditLog, cfg: SyslogConfig) -> str:
    """Render one audit-log row as an RFC5424 line (no framing).

    Carries every modeled column in a `[audit@tacacs-web …]` SD block.
    Failed-/expired-action codes raise severity from Info to Warning
    so SIEM routing can split them out.
    """
    severity = SEVERITY_WARNING if row.action in _WARNING_ACTIONS else SEVERITY_INFO
    pri = cfg.facility * 8 + severity
    ts = (
        row.ts.replace(tzinfo=UTC)
        if row.ts.tzinfo is None
        else row.ts.astimezone(UTC)
    )
    timestamp = ts.strftime("%Y-%m-%dT%H:%M:%S.") + f"{ts.microsecond // 1000:03d}Z"

    sd_parts: list[str] = [_sd_param("action", row.action)]
    if row.actor_username_snapshot:
        sd_parts.append(_sd_param("actor", row.actor_username_snapshot))
    if row.actor_role:
        sd_parts.append(_sd_param("role", row.actor_role))
    if row.auth_method:
        sd_parts.append(_sd_param("auth_method", row.auth_method))
    if row.target_type:
        sd_parts.append(_sd_param("target_type", row.target_type))
    if row.target_id is not None:
        sd_parts.append(_sd_param("target_id", str(row.target_id)))
    if row.client_ip:
        sd_parts.append(_sd_param("client_ip", row.client_ip))
    sd = "[audit@tacacs-web " + " ".join(sd_parts) + "]"

    summary = row.summary or row.action
    msg = (
        f"{row.actor_username_snapshot}: {summary}"
        if row.actor_username_snapshot
        else summary
    )

    header = f"<{pri}>1 {timestamp} {cfg.hostname} {cfg.app_name} - audit"
    return f"{header} {sd} {msg}"


# --- config / persistence -------------------------------------------------


async def _read_setting(session: AsyncSession, key: str) -> str | None:
    row = (
        await session.execute(select(SystemSetting).where(SystemSetting.key == key))
    ).scalar_one_or_none()
    return row.value if row is not None else None


async def _write_setting(session: AsyncSession, key: str, value: str | None) -> None:
    row = (
        await session.execute(select(SystemSetting).where(SystemSetting.key == key))
    ).scalar_one_or_none()
    if value is None:
        if row is not None:
            await session.delete(row)
        return
    if row is None:
        session.add(SystemSetting(key=key, value=value))
    else:
        row.value = value


async def _read_secret(session: AsyncSession, key: str) -> str | None:
    row = (
        await session.execute(select(SystemSecret).where(SystemSecret.key == key))
    ).scalar_one_or_none()
    return row.value if row is not None else None


async def load_config(session: AsyncSession) -> SyslogConfig:
    enabled = (await _read_setting(session, SETTING_ENABLED) or "false").lower() == "true"
    host = await _read_setting(session, SETTING_HOST) or ""
    port_raw = await _read_setting(session, SETTING_PORT) or "6514"
    try:
        port = int(port_raw)
    except ValueError:
        port = 6514
    protocol_raw = (await _read_setting(session, SETTING_PROTOCOL) or "tls").lower()
    protocol = "tls" if protocol_raw == "tls" else "tcp"
    fac_raw = await _read_setting(session, SETTING_FACILITY) or str(DEFAULT_FACILITY)
    try:
        facility = max(0, min(23, int(fac_raw)))
    except ValueError:
        facility = DEFAULT_FACILITY
    app_name = await _read_setting(session, SETTING_APP_NAME) or "tacacs-web"
    hostname = await _read_setting(session, SETTING_HOSTNAME) or "tacacs-web"
    tls_verify = (
        await _read_setting(session, SETTING_TLS_VERIFY) or "true"
    ).lower() == "true"
    return SyslogConfig(
        enabled=enabled,
        host=host,
        port=port,
        protocol=protocol,
        facility=facility,
        app_name=app_name,
        hostname=hostname,
        tls_verify=tls_verify,
        tls_server_name=await _read_setting(session, SETTING_TLS_SERVER_NAME),
        tls_ca_pem=await _read_secret(session, SECRET_TLS_CA_PEM),
        tls_client_cert_pem=await _read_secret(session, SECRET_TLS_CLIENT_CERT_PEM),
        tls_client_key_pem=await _read_secret(session, SECRET_TLS_CLIENT_KEY_PEM),
    )


# --- transport ------------------------------------------------------------


def _build_ssl_context(cfg: SyslogConfig) -> ssl.SSLContext:
    ctx = ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH)
    if cfg.tls_ca_pem:
        ctx.load_verify_locations(cadata=cfg.tls_ca_pem)
    if not cfg.tls_verify:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    if cfg.tls_client_cert_pem and cfg.tls_client_key_pem:
        # `load_cert_chain` requires files on disk; tempfile would work
        # but is messier. ssl.SSLContext.load_cert_chain has no in-memory
        # variant, so we write the pair to a tmp dir for the call.
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            cert_path = os.path.join(td, "client.crt")
            key_path = os.path.join(td, "client.key")
            with open(cert_path, "w", encoding="utf-8") as f:
                f.write(cfg.tls_client_cert_pem)
            with open(key_path, "w", encoding="utf-8") as f:
                f.write(cfg.tls_client_key_pem)
            ctx.load_cert_chain(cert_path, key_path)
    return ctx


def _send_lines(cfg: SyslogConfig, lines: list[str]) -> None:
    """Send `lines` (already RFC5424-formatted) via RFC6587 octet-counted framing.

    Raises on any transport-layer error. Synchronous; the async caller
    runs this via `asyncio.to_thread`.
    """
    if not cfg.host:
        raise RuntimeError("syslog.host is not configured")
    sock = socket.create_connection((cfg.host, cfg.port), timeout=SOCKET_TIMEOUT)
    try:
        if cfg.protocol == "tls":
            ssl_ctx = _build_ssl_context(cfg)
            server_hostname = cfg.tls_server_name or cfg.host
            sock = ssl_ctx.wrap_socket(sock, server_hostname=server_hostname)
        sock.settimeout(SOCKET_TIMEOUT)
        for line in lines:
            payload = line.encode("utf-8")
            frame = f"{len(payload)} ".encode("ascii") + payload
            sock.sendall(frame)
    finally:
        with contextlib.suppress(OSError):
            sock.close()


def send_test_message(cfg: SyslogConfig) -> None:
    """Open a connection, send one synthetic record, hang up. Raises on failure."""
    pri = cfg.facility * 8 + SEVERITY_INFO
    now = datetime.now(UTC)
    ts = now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"
    msg = (
        f"<{pri}>1 {ts} {cfg.hostname} {cfg.app_name} - test "
        f"[acct@tacacs-web test=\"connectivity\"] tacacs-web syslog reachability test"
    )
    _send_lines(cfg, [msg])


# --- loop -----------------------------------------------------------------


async def _record_error(error: str) -> None:
    async with SessionLocal() as s:
        await _write_setting(s, SETTING_LAST_ERROR, error)
        await _write_setting(s, SETTING_LAST_ERROR_AT, datetime.now(UTC).isoformat())
        await s.commit()


async def _clear_error() -> None:
    async with SessionLocal() as s:
        await _write_setting(s, SETTING_LAST_ERROR, None)
        await _write_setting(s, SETTING_LAST_ERROR_AT, None)
        await s.commit()


async def _process_one_batch() -> int:
    """Forward up to BATCH_SIZE new rows from each stream.

    Two independent streams ship through the same TCP/TLS connection:
    - accounting_record (offset key SETTING_LAST_ID)
    - audit_log         (offset key SETTING_LAST_AUDIT_ID)

    A NAS that doesn't run `aaa accounting` still produces audit_log
    rows for every authn/authz decision via the MAVIS handler, so
    the SIEM gets failed-login visibility even with accounting off.

    Returns the total number of lines sent across both streams.
    Returns 0 silently if syslog is disabled.
    Raises on transport failure so the loop can back off without
    advancing either offset.
    """
    async with SessionLocal() as s:
        cfg = await load_config(s)
        if not cfg.enabled or not cfg.host:
            return 0
        last_acct_raw = await _read_setting(s, SETTING_LAST_ID) or "0"
        last_acct = int(last_acct_raw) if last_acct_raw.isdigit() else 0
        last_audit_raw = await _read_setting(s, SETTING_LAST_AUDIT_ID) or "0"
        last_audit = int(last_audit_raw) if last_audit_raw.isdigit() else 0
        audit_rows = (
            await s.execute(
                select(AuditLog)
                .where(AuditLog.id > last_audit)
                .order_by(AuditLog.id)
                .limit(BATCH_SIZE)
            )
        ).scalars().all()
        acct_rows = (
            await s.execute(
                select(AccountingRecord)
                .where(AccountingRecord.id > last_acct)
                .order_by(AccountingRecord.id)
                .limit(BATCH_SIZE)
            )
        ).scalars().all()

    if not audit_rows and not acct_rows:
        return 0

    lines: list[str] = []
    lines.extend(format_rfc5424_audit(r, cfg) for r in audit_rows)
    lines.extend(format_rfc5424(r, cfg) for r in acct_rows)
    await asyncio.to_thread(_send_lines, cfg, lines)

    async with SessionLocal() as s:
        if audit_rows:
            await _write_setting(s, SETTING_LAST_AUDIT_ID, str(audit_rows[-1].id))
        if acct_rows:
            await _write_setting(s, SETTING_LAST_ID, str(acct_rows[-1].id))
        await s.commit()
    return len(lines)


async def _forwarder_loop() -> None:
    while True:
        try:
            n = await _process_one_batch()
            if n > 0:
                _log.info("syslog.forwarded", count=n)
                await _clear_error()
            await asyncio.sleep(POLL_SECONDS)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            _log.warning("syslog.forward_failed", error=str(exc))
            with contextlib.suppress(Exception):
                await _record_error(f"{exc.__class__.__name__}: {exc}")
            await asyncio.sleep(POLL_SECONDS * 3)


def start_forwarder() -> None:
    global _TASK
    if _TASK is not None and not _TASK.done():
        return
    _TASK = asyncio.create_task(_forwarder_loop(), name="syslog-forwarder")
    _log.info("syslog.forwarder_started")


async def stop_forwarder() -> None:
    global _TASK
    if _TASK is None:
        return
    _TASK.cancel()
    with contextlib.suppress(asyncio.CancelledError, Exception):
        await _TASK
    _TASK = None
    _log.info("syslog.forwarder_stopped")
