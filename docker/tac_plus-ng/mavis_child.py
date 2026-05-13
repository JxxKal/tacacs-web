#!/usr/bin/env python3
"""MAVIS external child for tac_plus-ng.

Long-lived child spawned by `tac_plus-ng`. Reads MAVIS request packets on
stdin, writes responses on stdout.

For each AUTH packet the child POSTs `{username, password}` to the backend's
`/internal/mavis/auth` endpoint; the backend resolves the user against the
DB, picks the configured LDAPEndpoint, and verifies the password by binding
to AD. The backend's verdict (ACK/NAK/NFD/ERR) becomes the MAVIS verdict.

INFO and HOST stay on the M2 permit-everything stub until M4 wires up the
per-user authorization story.

Wire protocol reference: see `mavis/perl/Mavis.pm` and
`mavis/perl/mavis_tacplus-ng-demo-database.pl` in MarcJHuber/event-driven-servers.
Each request is `<int_index> <value>\\n` lines terminated by `=\\n`.
Response uses the same format and terminates with `=<verdict>\\n` where
verdict 0 = MAVIS_FINAL. Newlines inside values are encoded as CR.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

AV_TYPE = 0
AV_USER = 4
AV_RESULT = 6
AV_PASSWORD = 8
AV_USER_RESPONSE = 32
AV_TACPROFILE = 48
AV_TACTYPE = 49

RESULT_OK = "ACK"
RESULT_FAIL = "NAK"
RESULT_NOTFOUND = "NFD"
RESULT_ERROR = "ERR"

MAVIS_FINAL = 0

BACKEND_URL = os.environ.get("TACACS_BACKEND_URL", "http://backend:8000").rstrip("/")
HTTP_TIMEOUT = float(os.environ.get("TACACS_BACKEND_TIMEOUT", "10"))

# Inline tac_plus-ng profile attached to every ACK'd AUTH. Permits any shell
# command so the smoke test can complete an authn round trip. Per-user
# profiles arrive in M4 once authz lands.
PERMIT_ALL_PROFILE = """{
    profile {
        script {
            if (service == shell) {
                if (cmd == "") {
                    set priv-lvl = 15
                    permit
                }
                permit
            }
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


def call_backend_auth(
    username: str,
    password: str,
    *,
    opener: object | None = None,
) -> tuple[str, str | None]:
    """POST one AUTH request to the backend. Returns (result, reason).

    `opener` lets the unit tests inject `urllib.request.build_opener(...)`
    to avoid hitting the network; if None we use the module-level urlopen.
    """
    body = json.dumps({"username": username, "password": password}).encode("utf-8")
    req = urllib.request.Request(
        f"{BACKEND_URL}/internal/mavis/auth",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        urlopen = opener.open if opener is not None else urllib.request.urlopen  # type: ignore[attr-defined]
        with urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return RESULT_ERROR, f"backend_http_{exc.code}"
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return RESULT_ERROR, f"backend_unreachable: {exc.__class__.__name__}"

    result = payload.get("result")
    if result not in {RESULT_OK, RESULT_FAIL, RESULT_NOTFOUND, RESULT_ERROR}:
        return RESULT_ERROR, "backend_bad_response"
    reason = payload.get("reason")
    return result, reason if isinstance(reason, str) else None


def handle(req: dict[int, str]) -> None:
    tactype = req.get(AV_TACTYPE, "")
    if tactype == "AUTH":
        username = req.get(AV_USER, "")
        password = req.get(AV_PASSWORD, "")
        result, _reason = call_backend_auth(username, password)
        req[AV_RESULT] = result
        if result == RESULT_OK:
            req[AV_TACPROFILE] = PERMIT_ALL_PROFILE
    elif tactype in {"INFO", "CHPW"}:
        # M4 will wire the per-user profile lookup. For now the daemon gets a
        # permit-everything inline profile so any authn'd user can run shell.
        req[AV_TACPROFILE] = PERMIT_ALL_PROFILE
        req[AV_RESULT] = RESULT_OK
    elif tactype == "HOST":
        # NAS hosts are still declared statically in tac_plus-ng.cfg in M3.
        req[AV_RESULT] = RESULT_OK
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
