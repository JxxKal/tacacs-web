"""Map a NAS source IP to a Device row.

Devices register either a host address ("192.0.2.10") or a CIDR block
("10.0.0.0/24") in `device.ip_or_cidr`. Longest-prefix wins on overlap, in
keeping with classic network-routing semantics (and CONTEXT.md / glossary).

We resolve in Python rather than via Postgres `inet`/`cidr` types because:
- the device table is operationally small (O(thousands at the high end);
- it keeps the unit-test path SQLite-friendly;
- the cost is amortised by MAVIS's authz cache (60s TTL, ADR-0001).
"""

from __future__ import annotations

import ipaddress
from collections.abc import Iterable

from app.db.models import Device


def resolve_device_for_ip(nas_ip: str, devices: Iterable[Device]) -> Device | None:
    """Pick the Device whose `ip_or_cidr` is the longest-prefix match for `nas_ip`.

    Returns None if no row contains the IP.

    A malformed `nas_ip` returns None (caller treats that as ERR). Devices with
    malformed `ip_or_cidr` are skipped silently — a strict integrity check
    belongs in the CRUD validation layer, not here.
    """
    try:
        addr = ipaddress.ip_address(nas_ip)
    except ValueError:
        return None

    best: tuple[int, Device] | None = None
    for device in devices:
        try:
            net = ipaddress.ip_network(device.ip_or_cidr, strict=False)
        except ValueError:
            continue
        if addr.version != net.version:
            continue
        if addr not in net:
            continue
        prefix_len = net.prefixlen
        if best is None or prefix_len > best[0]:
            best = (prefix_len, device)
    return best[1] if best else None
