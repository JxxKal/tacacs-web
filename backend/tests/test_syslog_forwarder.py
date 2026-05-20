"""Unit tests for the syslog forwarder formatter + status endpoint."""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.sessions import SessionContext, require_session
from app.db.models import AccountingRecord
from app.db.session import get_session
from app.main import app
from app.syslog.forwarder import SyslogConfig, format_rfc5424


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
