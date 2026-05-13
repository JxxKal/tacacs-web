"""Render `host` blocks for tac_plus-ng.cfg from Device rows.

One block per Device:

    host <safe_name> {
        address = <ip_or_cidr>
        key = "<current_secret>"
        key = "<previous_secret>"   # only present during a rotation window
        mavis backend = yes
    }

`safe_name` is the Device.name run through a strict identifier filter so it
can't break the surrounding tac_plus-ng grammar. Devices that lack a
`current_secret_enc` are skipped — they're unprovisioned and can't accept
TACACS traffic anyway.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from app.db.models import Device

_SAFE_NAME_CHARS = re.compile(r"[^A-Za-z0-9_]")


def _safe_block_name(name: str) -> str:
    """Strip everything that isn't `[A-Za-z0-9_]`; collapse repeats to one `_`.

    Empty after filtering -> "dev"; ensures every block has a stable label.
    """
    cleaned = _SAFE_NAME_CHARS.sub("_", name)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned or "dev"


def _escape_quoted(value: str) -> str:
    """Escape `\\` and `"` so the secret can sit inside a `key = "..."` literal."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def render_host_blocks(devices: Iterable[Device]) -> str:
    """Return the rendered config fragment, ending with a single trailing newline.

    Caller is expected to splice this into a `tac_plus-ng.cfg.template` slot
    and signal the daemon to reload.
    """
    blocks: list[str] = []
    seen_names: set[str] = set()
    for device in sorted(devices, key=lambda d: (d.name, d.id or 0)):
        if not device.current_secret_enc:
            continue
        safe = _safe_block_name(device.name)
        # Disambiguate name collisions deterministically by appending the id.
        if safe in seen_names:
            safe = f"{safe}_{device.id}"
        seen_names.add(safe)
        lines = [
            f"host {safe} {{",
            f"    address = {device.ip_or_cidr}",
            f'    key = "{_escape_quoted(device.current_secret_enc)}"',
        ]
        if device.previous_secret_enc:
            lines.append(f'    key = "{_escape_quoted(device.previous_secret_enc)}"')
        lines.append("    mavis backend = yes")
        lines.append("}")
        blocks.append("\n".join(lines))
    return ("\n\n".join(blocks) + "\n") if blocks else ""
