"""Unit tests for the syslog forwarder formatter + status endpoint."""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.sessions import SessionContext, require_session
from app.db.models import AccountingRecord, AuditLog
from app.db.session import get_session
from app.main import app
from app.syslog.forwarder import (
    SyslogConfig,
    format_rfc5424,
    format_rfc5424_audit,
)


def _cfg(**overrides: object) -> SyslogConfig:
    base = {
        "enabled": True,
        "host": "siem.example.com",
        "port": 6514,
        "protocol": "tls",
        "facility": 16,
        "app_name": "tacacs-web",
        "hostname": "tacacs-web",
        "tls_verify": True,
        "tls_server_name": None,
        "tls_ca_pem": None,
        "tls_client_cert_pem": None,
        "tls_client_key_pem": None,
    }
    base.update(overrides)
    return SyslogConfig(**base)  # type: ignore[arg-type]


def _record(**kwargs: object) -> AccountingRecord:
    rec = AccountingRecord(
        ts=kwargs.pop("ts", datetime(2026, 5, 20, 17, 0, 0, 123000, tzinfo=UTC)),
        nas_ip=kwargs.pop("nas_ip", "10.0.0.1"),
        username=kwargs.pop("username", "jan"),
        port=kwargs.pop("port", "vty0"),
        nac_ip=kwargs.pop("nac_ip", "10.0.0.50"),
        action=kwargs.pop("action", "start"),
        service=kwargs.pop("service", "shell"),
        cmd=kwargs.pop("cmd", None),
        priv_lvl=kwargs.pop("priv_lvl", None),
        elapsed_seconds=kwargs.pop("elapsed_seconds", None),
        task_id=kwargs.pop("task_id", "0a00b00c"),
        raw_av_pairs=kwargs.pop("raw_av_pairs", {}),
    )
    for k, v in kwargs.items():
        setattr(rec, k, v)
    return rec


def test_format_starts_with_pri_and_version() -> None:
    line = format_rfc5424(_record(), _cfg())
    # facility 16 * 8 + severity 6 = 134
    assert line.startswith("<134>1 ")


def test_format_includes_timestamp_with_zulu() -> None:
    line = format_rfc5424(_record(), _cfg())
    assert "2026-05-20T17:00:00.123Z" in line


def test_format_app_name_and_hostname_default() -> None:
    line = format_rfc5424(_record(), _cfg())
    parts = line.split(" ")
    # <PRI>1 TIMESTAMP HOSTNAME APP-NAME PROCID MSGID SD MSG
    assert parts[2] == "tacacs-web"  # hostname
    assert parts[3] == "tacacs-web"  # app name


def test_format_structured_data_contains_user_and_nas() -> None:
    line = format_rfc5424(
        _record(cmd="show running-config", priv_lvl=15, elapsed_seconds=42),
        _cfg(),
    )
    assert 'user="jan"' in line
    assert 'nas="10.0.0.1"' in line
    assert 'cmd="show running-config"' in line
    assert 'privlvl="15"' in line
    assert 'elapsed="42"' in line


def test_format_escapes_quotes_and_brackets_in_sd() -> None:
    rec = _record(cmd='echo "hi" ]end')
    line = format_rfc5424(rec, _cfg())
    # The cmd value should appear escaped inside the SD block.
    sd = line[line.index("[acct@") : line.index("]") + 1]
    # Escape isn't terminal-perfect: just confirm the parser-breakers
    # got at least their RFC5424 escape.
    assert '\\"hi\\"' in sd


def test_format_msg_body_human_readable() -> None:
    line = format_rfc5424(_record(cmd="show ip route"), _cfg())
    # The body comes after the closing `]` of the SD block.
    body = line.rsplit("] ", 1)[1]
    assert body == "jan: show ip route"


def test_format_handles_naive_timestamp() -> None:
    rec = _record(ts=datetime(2026, 5, 20, 17, 0, 0, 0))
    line = format_rfc5424(rec, _cfg())
    # Falls back to UTC interpretation.
    assert re.search(r"2026-05-20T17:00:00\.000Z", line)


# --------------- audit-log formatter -------------------------------------


def _audit(**kwargs: object) -> AuditLog:
    row = AuditLog(
        ts=kwargs.pop("ts", datetime(2026, 5, 20, 17, 0, 0, 0, tzinfo=UTC)),
        actor_id=kwargs.pop("actor_id", 1),
        actor_username_snapshot=kwargs.pop("actor_username_snapshot", "alice"),
        actor_role=kwargs.pop("actor_role", "admin"),
        auth_method=kwargs.pop("auth_method", "tacacs"),
        action=kwargs.pop("action", "tacacs.authn_succeeded"),
        target_type=kwargs.pop("target_type", "device"),
        target_id=kwargs.pop("target_id", 42),
        summary=kwargs.pop("summary", "shell login ok"),
        client_ip=kwargs.pop("client_ip", "10.0.0.50"),
        user_agent=kwargs.pop("user_agent", None),
    )
    for k, v in kwargs.items():
        setattr(row, k, v)
    return row


def test_audit_format_pri_info_severity_for_success() -> None:
    line = format_rfc5424_audit(_audit(action="tacacs.authn_succeeded"), _cfg())
    # facility 16 * 8 + severity 6 = 134
    assert line.startswith("<134>1 ")


def test_audit_format_pri_warning_severity_for_failure() -> None:
    line = format_rfc5424_audit(_audit(action="tacacs.authn_failed"), _cfg())
    # facility 16 * 8 + severity 4 = 132
    assert line.startswith("<132>1 ")


def test_audit_format_carries_modeled_columns_in_sd() -> None:
    line = format_rfc5424_audit(_audit(), _cfg())
    assert 'action="tacacs.authn_succeeded"' in line
    assert 'actor="alice"' in line
    assert 'role="admin"' in line
    assert 'auth_method="tacacs"' in line
    assert 'target_type="device"' in line
    assert 'target_id="42"' in line
    assert 'client_ip="10.0.0.50"' in line


def test_audit_format_msg_body_prefixes_with_actor() -> None:
    line = format_rfc5424_audit(_audit(summary="bad password"), _cfg())
    body = line.rsplit("] ", 1)[1]
    assert body == "alice: bad password"


def test_audit_format_msgid_is_audit() -> None:
    line = format_rfc5424_audit(_audit(), _cfg())
    # <PRI>1 TIMESTAMP HOSTNAME APP-NAME PROCID MSGID ...
    parts = line.split(" ", 6)
    assert parts[5] == "audit"


# --------------- transport -----------------------------------------------


def test_udp_send_emits_one_datagram_per_line(monkeypatch: pytest.MonkeyPatch) -> None:
    """UDP path must not octet-frame; each line goes as its own datagram."""
    from app.syslog import forwarder as fwd

    sent: list[tuple[bytes, tuple[str, int]]] = []

    class _FakeUdpSocket:
        def settimeout(self, _t: float) -> None:
            pass

        def sendto(self, data: bytes, addr: tuple[str, int]) -> None:
            sent.append((data, addr))

        def close(self) -> None:
            pass

    def _fake_socket(family: int, type_: int) -> _FakeUdpSocket:
        assert family == fwd.socket.AF_INET
        assert type_ == fwd.socket.SOCK_DGRAM
        return _FakeUdpSocket()

    monkeypatch.setattr(fwd.socket, "socket", _fake_socket)

    cfg = _cfg(protocol="udp", port=514)
    lines = ["<134>1 - - - - - line-a", "<134>1 - - - - - line-b"]
    fwd._send_lines(cfg, lines)

    assert len(sent) == 2
    assert sent[0][0].startswith(b"<134>1 ")
    # No RFC6587 length prefix (would start with ASCII digit + space).
    assert b" line-a" in sent[0][0]
    assert all(addr == ("siem.example.com", 514) for _payload, addr in sent)


def test_udp_send_truncates_oversize_datagram(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.syslog import forwarder as fwd

    captured: list[bytes] = []

    class _FakeUdpSocket:
        def settimeout(self, _t: float) -> None:
            pass

        def sendto(self, data: bytes, _addr: tuple[str, int]) -> None:
            captured.append(data)

        def close(self) -> None:
            pass

    monkeypatch.setattr(fwd.socket, "socket", lambda *_a, **_kw: _FakeUdpSocket())

    cfg = _cfg(protocol="udp", port=514)
    big = "X" * (fwd.UDP_MAX_BYTES + 200)
    fwd._send_lines(cfg, [big])
    assert len(captured) == 1
    assert len(captured[0]) <= fwd.UDP_MAX_BYTES
    assert captured[0].endswith(b"...[truncated]")


# --------------- endpoint -------------------------------------------------


def _ctx(role: str = "admin") -> SessionContext:
    return SessionContext(
        token="test-token",
        username=f"test-{role}",
        role=role,
        auth_method="local",
        actor_id=1,
        client_ip="127.0.0.1",
        user_agent="pytest",
    )


@pytest.fixture
def admin_client(async_db_session: AsyncSession) -> Iterator[TestClient]:
    async def _override_session() -> AsyncIterator[AsyncSession]:
        yield async_db_session

    async def _override_require_session() -> SessionContext:
        return _ctx("admin")

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[require_session] = _override_require_session
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.clear()


def test_default_status_disabled(admin_client: TestClient) -> None:
    r = admin_client.get("/api/v1/settings/syslog")
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is False
    assert body["protocol"] == "tls"
    assert body["facility"] == 16


def test_update_persists_and_status_reflects(admin_client: TestClient) -> None:
    r = admin_client.put(
        "/api/v1/settings/syslog",
        json={
            "enabled": True,
            "host": "siem.example.com",
            "port": 6514,
            "protocol": "tls",
            "facility": 17,
            "app_name": "tacacs-web",
            "hostname": "tacacs1",
            "tls_verify": True,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["enabled"] is True
    assert body["host"] == "siem.example.com"
    assert body["facility"] == 17
    assert body["hostname"] == "tacacs1"


def test_update_rejects_out_of_range_facility(admin_client: TestClient) -> None:
    r = admin_client.put(
        "/api/v1/settings/syslog",
        json={
            "enabled": True,
            "host": "siem.example.com",
            "port": 6514,
            "protocol": "tls",
            "facility": 99,
            "app_name": "tacacs-web",
            "hostname": "tacacs1",
            "tls_verify": True,
        },
    )
    assert r.status_code == 422
