"""Unit tests for the accounting log parser."""

from __future__ import annotations

from datetime import UTC, datetime

from app.accounting.ingestor import parse_record


def test_parse_record_canonical_shell_start() -> None:
    # Eight tab-separated fields; iso timestamp.
    line = (
        "2026-05-20T17:00:00+00:00\t10.0.0.1\tjan\tvty0\t10.0.0.50\t"
        "0a00b00c\tstart\tservice=shell task_id=42 priv-lvl=15"
    )
    rec = parse_record(line)
    assert rec is not None
    assert rec["nas_ip"] == "10.0.0.1"
    assert rec["username"] == "jan"
    assert rec["port"] == "vty0"
    assert rec["nac_ip"] == "10.0.0.50"
    assert rec["task_id"] == "0a00b00c"
    assert rec["action"] == "start"
    assert rec["av_pairs"] == {
        "service": "shell",
        "task_id": "42",
        "priv-lvl": "15",
    }
    assert isinstance(rec["ts"], datetime)
    assert rec["ts"].tzinfo is not None


def test_parse_record_quoted_command() -> None:
    line = (
        "2026-05-20T17:00:00+00:00\t10.0.0.1\tjan\tvty0\t10.0.0.50\t"
        '0a00b00c\tstop\tservice=shell cmd="show running-config" '
        "priv-lvl=15 elapsed_time=42"
    )
    rec = parse_record(line)
    assert rec is not None
    args = rec["av_pairs"]
    assert isinstance(args, dict)
    assert args["cmd"] == "show running-config"
    assert args["elapsed_time"] == "42"


def test_parse_record_empty_optionals() -> None:
    # Console session: no port, no nac.
    line = (
        "2026-05-20T17:00:00+00:00\t10.0.0.1\troot\t\t\t"
        "deadbeef\tstart\tservice=shell"
    )
    rec = parse_record(line)
    assert rec is not None
    assert rec["port"] is None
    assert rec["nac_ip"] is None


def test_parse_record_unix_epoch_ts() -> None:
    line = (
        "1716224400\t10.0.0.1\tjan\tvty0\t10.0.0.50\t"
        "0a00b00c\tstart\tservice=shell"
    )
    rec = parse_record(line)
    assert rec is not None
    ts = rec["ts"]
    assert isinstance(ts, datetime)
    assert ts == datetime.fromtimestamp(1716224400, tz=UTC)


def test_parse_record_ctime_ts() -> None:
    line = (
        "Tue May 20 17:00:00 2026\t10.0.0.1\tjan\tvty0\t10.0.0.50\t"
        "0a00b00c\tstart\tservice=shell"
    )
    rec = parse_record(line)
    assert rec is not None
    assert isinstance(rec["ts"], datetime)


def test_parse_record_args_tab_separated() -> None:
    # tac_plus-ng sometimes joins ${args} with tabs instead of spaces.
    line = "2026-05-20T17:00:00+00:00\t10.0.0.1\tjan\tvty0\t10.0.0.50\t" \
        "0a00b00c\tstart\tservice=shell\tcmd=show\tpriv-lvl=15"
    rec = parse_record(line)
    assert rec is not None
    assert rec["av_pairs"] == {
        "service": "shell",
        "cmd": "show",
        "priv-lvl": "15",
    }


def test_parse_record_blank_line_skipped() -> None:
    assert parse_record("") is None
    assert parse_record("\n") is None
    # Too few fields -> reject.
    assert parse_record("garbage") is None


def test_parse_record_malformed_quoting_falls_back() -> None:
    # Unclosed quote: shlex would raise; we fall back to whitespace split.
    line = (
        "2026-05-20T17:00:00+00:00\t10.0.0.1\tjan\tvty0\t10.0.0.50\t"
        '0a00b00c\tstop\tservice=shell cmd="never-closed'
    )
    rec = parse_record(line)
    assert rec is not None
    args = rec["av_pairs"]
    # Should still capture service=shell; cmd may be partial.
    assert args.get("service") == "shell"
