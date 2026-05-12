#!/usr/bin/env python3
"""MAVIS external child for tac_plus-ng (M2 stub).

Long-lived child spawned by `tac_plus-ng`. Reads MAVIS request packets on
stdin, writes responses on stdout. For now (M2) every authentication request
is answered with RESULT=ACK so the smoke test can verify the end-to-end
TACACS+ <-> daemon <-> MAVIS round trip. No DB or LDAP yet — those land
in M3.

Wire protocol (see `mavis/python/mavis.py` in MarcJHuber/event-driven-servers):

    Request from daemon:
        <int_index> <value>\\n   (one per AV-pair)
        =\\n                     (terminator)

    Response to daemon:
        <int_index> <value>\\n
        =<verdict>\\n            (verdict 0 = MAVIS_FINAL)

AV-pair indices we touch here: 0=TYPE 4=USER 6=RESULT 8=PASSWORD
32=USER_RESPONSE 49=TACTYPE.
"""

from __future__ import annotations

import sys

AV_TYPE = 0
AV_USER = 4
AV_RESULT = 6
AV_PASSWORD = 8
AV_USER_RESPONSE = 32
AV_TACTYPE = 49

MAVIS_FINAL = 0


def read_request() -> dict[int, str] | None:
    """Return one parsed MAVIS request, or None at EOF."""
    req: dict[int, str] = {}
    while True:
        line = sys.stdin.readline()
        if not line:
            return None
        line = line.rstrip("\n")
        if line == "=":
            return req
        idx_str, _, value = line.partition(" ")
        try:
            idx = int(idx_str)
        except ValueError:
            continue
        req[idx] = value


def write_response(av: dict[int, str], result: str) -> None:
    """Send an ACK/NAK/ERR response back to the daemon."""
    av[AV_RESULT] = result
    for idx in sorted(av):
        # Newlines in values are escaped to CR per protocol convention.
        value = av[idx].replace("\n", "\r")
        sys.stdout.write(f"{idx} {value}\n")
    sys.stdout.write(f"={MAVIS_FINAL}\n")
    sys.stdout.flush()


def handle(req: dict[int, str]) -> None:
    tactype = req.get(AV_TACTYPE, "")
    # M2 stub: accept every AUTH request. INFO/HOST/etc. also accepted so the
    # daemon can complete its protocol dance without spurious NAKs.
    if tactype in {"AUTH", "INFO", "HOST"}:
        write_response(req, "ACK")
    else:
        write_response(req, "ACK")


def main() -> int:
    while True:
        req = read_request()
        if req is None:
            return 0
        handle(req)


if __name__ == "__main__":
    sys.exit(main())
