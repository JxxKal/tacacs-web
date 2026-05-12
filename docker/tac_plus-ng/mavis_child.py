#!/usr/bin/env python3
"""MAVIS external child for tac_plus-ng (M2 stub).

Long-lived child spawned by `tac_plus-ng`. Reads MAVIS request packets on
stdin, writes responses on stdout. For M2 every user is accepted with a
permit-everything profile so the smoke test can complete an authn round
trip. M3 swaps in real DB + LDAPS lookups and per-user profiles.

Wire protocol reference:
  mavis/perl/Mavis.pm and mavis/perl/mavis_tacplus-ng-demo-database.pl
  in MarcJHuber/event-driven-servers.

Each request is `<int_index> <value>\\n` lines terminated by `=\\n`.
Response uses the same format and terminates with `=<verdict>\\n` where
verdict 0 = MAVIS_FINAL.
"""

from __future__ import annotations

import sys

# AV-pair indices.
AV_TYPE = 0
AV_USER = 4
AV_RESULT = 6
AV_PASSWORD = 8
AV_USER_RESPONSE = 32
AV_TACPROFILE = 48
AV_TACTYPE = 49

# Result codes.
RESULT_OK = "ACK"
RESULT_FAIL = "NAK"
RESULT_NOTFOUND = "NFD"
RESULT_ERROR = "ERR"

MAVIS_FINAL = 0

# tac_plus-ng config snippet returned for every INFO lookup in M2. Binds the
# user to a profile that permits any shell session. Newlines are converted
# to CR on the wire (protocol convention), the daemon decodes them back.
PERMIT_ALL_PROFILE = """{
    profile {
        script {
            permit
        }
    }
}"""


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


def write_response(av: dict[int, str]) -> None:
    for idx in sorted(av):
        value = av[idx].replace("\n", "\r")
        sys.stdout.write(f"{idx} {value}\n")
    sys.stdout.write(f"={MAVIS_FINAL}\n")
    sys.stdout.flush()


def handle(req: dict[int, str]) -> None:
    tactype = req.get(AV_TACTYPE, "")
    if tactype == "AUTH":
        # M2 stub: accept any password. M3 will run a live LDAPS bind here.
        req[AV_RESULT] = RESULT_OK
    elif tactype == "INFO":
        # Hand back a permit-everything inline profile.
        req[AV_TACPROFILE] = PERMIT_ALL_PROFILE
        req[AV_RESULT] = RESULT_OK
    elif tactype == "HOST":
        # Hosts are declared statically in tac_plus-ng.cfg in M2; tell MAVIS
        # we don't know the host so the daemon falls back to the static block.
        req[AV_RESULT] = RESULT_NOTFOUND
    else:
        req[AV_RESULT] = RESULT_FAIL
    write_response(req)


def main() -> int:
    while True:
        req = read_request()
        if req is None:
            return 0
        handle(req)


if __name__ == "__main__":
    sys.exit(main())
