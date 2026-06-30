"""Unit tests for `docker/tac_plus-ng/mavis_child.py`.

The child runs in the tac_plus-ng container (stdlib-only Python) so its
tests live here in the backend test suite but load the script by path
rather than importing as `mavis_child` — there's no package, no install.
"""

from __future__ import annotations

import importlib.util
import io
import json
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest


def _load_mavis_child() -> ModuleType:
    here = Path(__file__).resolve()
    script = here.parents[2] / "docker" / "tac_plus-ng" / "mavis_child.py"
    spec = importlib.util.spec_from_file_location("mavis_child_under_test", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def mc() -> ModuleType:
    return _load_mavis_child()


class _FakeOpener:
    """Mimics `urllib.request.OpenerDirector` with a canned response body."""

    def __init__(self, payload: dict[str, Any], status: int = 200) -> None:
        self.payload = payload
        self.status = status
        self.last_request: Any = None
        self.last_timeout: float | None = None

    def open(self, req: Any, timeout: float | None = None) -> Any:
        self.last_request = req
        self.last_timeout = timeout
        body = json.dumps(self.payload).encode("utf-8")
        return _FakeResponse(body)


class _FakeResponse:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body


def test_call_backend_auth_returns_ack(mc: ModuleType) -> None:
    opener = _FakeOpener({"result": "ACK", "reason": None})
    result, reason = mc.call_backend_auth("jan", "hunter2", opener=opener)
    assert (result, reason) == ("ACK", None)
    body = json.loads(opener.last_request.data.decode())
    assert body == {"username": "jan", "password": "hunter2"}
    assert opener.last_request.full_url.endswith("/internal/mavis/auth")


def test_call_backend_auth_returns_nak(mc: ModuleType) -> None:
    opener = _FakeOpener({"result": "NAK", "reason": "wrong_password"})
    assert mc.call_backend_auth("jan", "nope", opener=opener) == ("NAK", "wrong_password")


def test_call_backend_auth_unreachable(mc: ModuleType) -> None:
    class Boom:
        def open(self, _req: Any, timeout: float | None = None) -> Any:
            raise OSError("connection refused")

    result, reason = mc.call_backend_auth("jan", "x", opener=Boom())
    assert result == "ERR"
    assert reason and reason.startswith("backend_unreachable")


def test_call_backend_auth_bad_response_shape(mc: ModuleType) -> None:
    opener = _FakeOpener({"result": "WHAT"})
    assert mc.call_backend_auth("jan", "x", opener=opener) == ("ERR", "backend_bad_response")


def test_handle_auth_attaches_profile_via_info_piggyback(
    mc: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """tac_plus-ng's check_access denies with `denied by ACL` if the user
    profile isn't attached on the AUTH response. Mirror the upstream
    MAVIS demo by piggybacking the INFO profile onto a successful AUTH.
    """
    captured: list[tuple[str, str]] = []

    def fake_info(
        username: str, nas_ip: str, *, opener: object | None = None
    ) -> tuple[str, str | None, str | None]:
        captured.append((username, nas_ip))
        return "ACK", None, "{ profile { script { permit } } }"

    monkeypatch.setattr(
        mc, "call_backend_auth", lambda u, p, *, nas_ip="", opener=None: ("ACK", None)
    )
    monkeypatch.setattr(mc, "call_backend_info", fake_info)
    out = _capture_response(
        mc,
        {
            mc.AV_TACTYPE: "AUTH",
            mc.AV_USER: "jan",
            mc.AV_PASSWORD: "x",
            mc.AV_SERVERIP: "10.1.2.3",
        },
    )
    assert out[mc.AV_RESULT] == "ACK"
    assert "permit" in out[mc.AV_TACPROFILE]
    assert captured == [("jan", "10.1.2.3")]


def test_handle_auth_skips_info_piggyback_without_nas_ip(
    mc: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If somehow AV_SERVERIP isn't set, AUTH still returns ACK but no
    profile (rather than crashing on the empty nas_ip)."""
    monkeypatch.setattr(
        mc, "call_backend_auth", lambda u, p, *, nas_ip="", opener=None: ("ACK", None)
    )

    def fake_info_must_not_run(*_a: object, **_k: object) -> tuple[str, str | None, str | None]:
        raise AssertionError("call_backend_info should not run without nas_ip")

    monkeypatch.setattr(mc, "call_backend_info", fake_info_must_not_run)
    out = _capture_response(mc, {mc.AV_TACTYPE: "AUTH", mc.AV_USER: "jan", mc.AV_PASSWORD: "x"})
    assert out[mc.AV_RESULT] == "ACK"
    assert mc.AV_TACPROFILE not in out


def test_handle_auth_nak_no_profile(mc: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        mc, "call_backend_auth", lambda u, p, *, nas_ip="", opener=None: ("NAK", "wrong_password")
    )
    out = _capture_response(mc, {mc.AV_TACTYPE: "AUTH", mc.AV_USER: "jan", mc.AV_PASSWORD: "x"})
    assert out[mc.AV_RESULT] == "NAK"
    assert mc.AV_TACPROFILE not in out


def test_handle_info_ack_attaches_profile(mc: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[tuple[str, str]] = []

    def fake_info(
        username: str, nas_ip: str, *, opener: object | None = None
    ) -> tuple[str, str | None, str | None]:
        captured.append((username, nas_ip))
        return "ACK", None, "{ profile { script { permit } } }"

    monkeypatch.setattr(mc, "call_backend_info", fake_info)
    out = _capture_response(
        mc,
        {mc.AV_TACTYPE: "INFO", mc.AV_USER: "jan", mc.AV_SERVERIP: "10.1.2.3"},
    )
    assert out[mc.AV_RESULT] == "ACK"
    assert "permit" in out[mc.AV_TACPROFILE]
    assert captured == [("jan", "10.1.2.3")]


def test_handle_info_nak_no_profile(mc: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        mc,
        "call_backend_info",
        lambda u, n, *, opener=None: ("NAK", "no_authorization", None),
    )
    out = _capture_response(
        mc,
        {mc.AV_TACTYPE: "INFO", mc.AV_USER: "jan", mc.AV_SERVERIP: "10.1.2.3"},
    )
    assert out[mc.AV_RESULT] == "NAK"
    assert mc.AV_TACPROFILE not in out


def test_handle_chpw_fails(mc: ModuleType) -> None:
    out = _capture_response(mc, {mc.AV_TACTYPE: "CHPW", mc.AV_USER: "jan"})
    assert out[mc.AV_RESULT] == "NAK"


def test_handle_host_ack_without_profile(mc: ModuleType) -> None:
    out = _capture_response(mc, {mc.AV_TACTYPE: "HOST"})
    assert out[mc.AV_RESULT] == "ACK"
    assert mc.AV_TACPROFILE not in out


def _capture_response(mc: ModuleType, req: dict[int, str]) -> dict[int, str]:
    """Drive `handle` once and parse the textual response back into a dict."""
    buf = io.StringIO()

    class _StdoutPatch:
        def __enter__(self) -> None:
            self._real = mc.sys.stdout
            mc.sys.stdout = buf

        def __exit__(self, *exc: object) -> None:
            mc.sys.stdout = self._real

    with _StdoutPatch():
        mc.handle(dict(req))
    return _parse_response(buf.getvalue())


def _parse_response(text: str) -> dict[int, str]:
    out: dict[int, str] = {}
    # Split on \n only — the wire format encodes value-internal newlines as
    # \r, and `str.splitlines()` would split on those too.
    for raw in text.split("\n"):
        if not raw or raw.startswith("="):
            continue
        idx_str, _, value = raw.partition(" ")
        out[int(idx_str)] = value.replace("\r", "\n")
    return out


@pytest.fixture(autouse=True)
def _restore_stdout() -> Iterator[None]:
    yield
