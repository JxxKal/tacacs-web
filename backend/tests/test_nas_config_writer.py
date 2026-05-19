"""Tests for the NAS-config persistence layer."""

from __future__ import annotations

import os

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Device, DeviceGroup
from app.nas_config import HOSTS_FILE, regenerate_nas_config


@pytest.fixture(autouse=True)
def _clean_hosts_file() -> None:
    if HOSTS_FILE.exists():
        HOSTS_FILE.unlink()


async def test_regen_writes_fallback_when_no_devices(
    async_db_session: AsyncSession,
) -> None:
    os.environ["TACACS_SHARED_SECRET"] = "smoke-fallback"
    try:
        content = await regenerate_nas_config(async_db_session)
    finally:
        os.environ.pop("TACACS_SHARED_SECRET", None)
    assert HOSTS_FILE.exists()
    assert HOSTS_FILE.read_text() == content
    assert "host bootstrap" in content
    assert 'key = "smoke-fallback"' in content


async def test_regen_renders_device_rows(
    async_db_session: AsyncSession,
) -> None:
    dg = DeviceGroup(name="core")
    async_db_session.add(dg)
    await async_db_session.commit()
    await async_db_session.refresh(dg)
    async_db_session.add(
        Device(
            name="core-sw-01",
            ip_or_cidr="10.0.0.1",
            device_group_id=dg.id,
            current_secret_enc="abc123",
        )
    )
    await async_db_session.commit()

    content = await regenerate_nas_config(async_db_session)
    assert "host core_sw_01" in content
    assert 'key = "abc123"' in content
    assert "host bootstrap" not in content


async def test_regen_skips_unprovisioned_device(
    async_db_session: AsyncSession,
) -> None:
    dg = DeviceGroup(name="core")
    async_db_session.add(dg)
    await async_db_session.commit()
    await async_db_session.refresh(dg)
    async_db_session.add(
        Device(
            name="empty-sw",
            ip_or_cidr="10.0.0.2",
            device_group_id=dg.id,
            current_secret_enc=None,
        )
    )
    await async_db_session.commit()

    os.environ["TACACS_SHARED_SECRET"] = "boot-secret"
    try:
        content = await regenerate_nas_config(async_db_session)
    finally:
        os.environ.pop("TACACS_SHARED_SECRET", None)
    # No provisioned device -> falls back to the bootstrap block.
    assert "host empty_sw" not in content
    assert "host bootstrap" in content


async def test_regen_writes_empty_when_no_devices_and_no_fallback_env(
    async_db_session: AsyncSession,
) -> None:
    os.environ.pop("TACACS_SHARED_SECRET", None)
    content = await regenerate_nas_config(async_db_session)
    assert content == ""
    assert HOSTS_FILE.exists()
    assert HOSTS_FILE.read_text() == ""
