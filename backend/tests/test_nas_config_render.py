"""Unit tests for `render_host_blocks`."""

from __future__ import annotations

from app.db.models import Device
from app.nas_config import render_host_blocks


def _device(
    *,
    name: str = "core-sw-01",
    ip: str = "10.0.0.1",
    current: str | None = "shhh",
    previous: str | None = None,
    id_: int = 1,
) -> Device:
    d = Device(name=name, ip_or_cidr=ip, device_group_id=1)
    d.id = id_
    d.current_secret_enc = current
    d.previous_secret_enc = previous
    return d


def test_render_single_device_no_previous() -> None:
    out = render_host_blocks([_device()])
    assert "host core_sw_01 {" in out
    assert "address = 10.0.0.1" in out
    assert 'key = "shhh"' in out
    # Only one key line when no rotation in progress.
    assert out.count("key =") == 1
    assert "mavis backend = yes" in out


def test_render_device_during_rotation_emits_both_keys() -> None:
    out = render_host_blocks([_device(current="new", previous="old")])
    keys = [line.strip() for line in out.splitlines() if line.strip().startswith("key =")]
    assert keys == ['key = "new"', 'key = "old"']


def test_render_skips_devices_without_current_secret() -> None:
    out = render_host_blocks([_device(name="provisioned", current="x"), _device(name="empty", current=None, id_=2)])
    assert "host provisioned {" in out
    assert "host empty" not in out


def test_render_sanitises_block_name() -> None:
    out = render_host_blocks([_device(name="core sw 01 / spine", id_=42)])
    assert "host core_sw_01_spine {" in out


def test_render_disambiguates_colliding_safe_names() -> None:
    out = render_host_blocks(
        [
            _device(name="a/b", id_=1),
            _device(name="a-b", id_=2, ip="10.0.0.2"),
        ]
    )
    # First (alphabetical by raw name): a-b -> a_b. Second: a/b -> a_b collides
    # -> a_b_1. The exact id used for the disambiguation is the second device's.
    assert out.count("host a_b ") == 1
    assert "host a_b_1 {" in out


def test_render_returns_empty_string_when_no_provisioned_devices() -> None:
    assert render_host_blocks([_device(current=None)]) == ""
    assert render_host_blocks([]) == ""


def test_render_escapes_secret_quote_and_backslash() -> None:
    out = render_host_blocks([_device(current='shh"ssh\\here')])
    # Backslash escaped first, then double-quote.
    assert 'key = "shh\\"ssh\\\\here"' in out


def test_render_emits_one_trailing_newline() -> None:
    out = render_host_blocks([_device()])
    assert out.endswith("\n")
    assert not out.endswith("\n\n")
