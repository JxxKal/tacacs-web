"""Persist the rendered NAS-host blocks to the shared tac_plus-ng volume.

`regenerate_nas_config` reads every Device row, runs the M4 renderer,
and writes the result to a known path the tac_plus-ng container watches
with inotify. The daemon-side sidecar SIGHUPs tac_plus-ng on file
change, so the new hosts go live without a container restart.

Empty DB or no-secret-yet edge case: the function still writes a file
— a single catch-all `host` block using the env-supplied
`TACACS_SHARED_SECRET`, so the daemon keeps accepting smoke / break-in
traffic while the operator provisions real Devices.
"""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Device
from app.nas_config.render import render_host_blocks

NAS_CONFIG_DIR = Path(
    os.environ.get("TACACS_WEB_NAS_CONFIG_DIR", "/var/lib/tacacs-web/tac_plus-ng")
)
HOSTS_FILE = NAS_CONFIG_DIR / "hosts.cfg"


def _fallback_block(shared_secret: str) -> str:
    """Catch-all `host` block used when no provisioned Device exists yet.

    Mirrors the bootstrap block the M2 entrypoint used to ship statically.
    Lets operators reach the daemon during initial setup before any Device
    rows exist.
    """
    safe_secret = shared_secret.replace("\\", "\\\\").replace('"', '\\"')
    return (
        "host bootstrap {\n"
        "    address = 0.0.0.0/0\n"
        f'    key = "{safe_secret}"\n'
        "    mavis backend = yes\n"
        "}\n"
    )


async def regenerate_nas_config(session: AsyncSession) -> str:
    """Re-render the hosts file from the Device table. Returns the new content.

    Called after every Device mutate (create/update/delete/rotate/retire)
    plus from an explicit admin endpoint. Idempotent: writing the same
    file twice is a no-op as far as the daemon is concerned (mtime
    bumps, the inotify sidecar coalesces and SIGHUPs anyway).
    """
    devices = (await session.execute(select(Device))).scalars().all()
    rendered = render_host_blocks(devices)
    if not rendered:
        shared_secret = os.environ.get("TACACS_SHARED_SECRET", "")
        if shared_secret:
            rendered = _fallback_block(shared_secret)
    NAS_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    HOSTS_FILE.write_text(rendered, encoding="utf-8")
    HOSTS_FILE.chmod(0o644)
    return rendered
