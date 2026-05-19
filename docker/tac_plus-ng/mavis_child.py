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
AV_IPADDR = 14
AV_SERVERIP = 25
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


def _post_json(
    path: str,
    payload: dict[str, str],
    *,
    opener: object | None = None,
) -> tuple[str, str | None, str | None]:
    """POST `payload` as JSON to `BACKEND_URL + path`. Returns (result, reason, profile).

    `profile` is only set on `/info` responses; for `/auth` it's always None.
    `opener` exists so unit tests can substitute an `OpenerDirector`-like
    object and skip the network entirely.
    """
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{BACKEND_URL}{path}",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        urlopen = opener.open if opener is not None else urllib.request.urlopen  # type: ignore[attr-defined]
        with urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            response = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return RESULT_ERROR, f"backend_http_{exc.code}", None
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return RESULT_ERROR, f"backend_unreachable: {exc.__class__.__name__}", None

    result = response.get("result")
    if result not in {RESULT_OK, RESULT_FAIL, RESULT_NOTFOUND, RESULT_ERROR}:
        return RESULT_ERROR, "backend_bad_response", None
    reason = response.get("reason") if isinstance(response.get("reason"), str) else None
    profile = response.get("profile") if isinstance(response.get("profile"), str) else None
    return result, reason, profile


def call_backend_auth(
    username: str,
    password: str,
    *,
    nas_ip: str = "",
    opener: object | None = None,
) -> tuple[str, str | None]:
    """`nas_ip` is optional but recommended — the backend records it as
    the client_ip on the audit-log row for the AUTH event."""
    payload: dict[str, str] = {"username": username, "password": password}
    if nas_ip:
        payload["nas_ip"] = nas_ip
    result, reason, _profile = _post_json(
        "/internal/mavis/auth",
        payload,
        opener=opener,
    )
    return result, reason


def call_backend_info(
    username: str, nas_ip: str, *, opener: object | None = None
) -> tuple[str, str | None, str | None]:
    return _post_json(
        "/internal/mavis/info",
        {"username": username, "nas_ip": nas_ip},
        opener=opener,
    )


def handle(req: dict[int, str]) -> None:
    tactype = req.get(AV_TACTYPE, "")
    if tactype == "AUTH":
        username = req.get(AV_USER, "")
        password = req.get(AV_PASSWORD, "")
        nas_ip = req.get(AV_SERVERIP, "")
        result, _reason = call_backend_auth(username, password, nas_ip=nas_ip)
        req[AV_RESULT] = result
        # tac_plus-ng's check_access path needs `user->profile` to be set
        # on a successful AUTH — otherwise eval_ruleset returns S_unknown
        # and the daemon emits "denied by ACL". Upstream's MAVIS demo
        # therefore returns the user profile on every response (AUTH and
        # INFO alike). Mirror that here by piggybacking an INFO lookup
        # on top of an ACK'd AUTH and attaching the resulting profile.
        if result == RESULT_OK and nas_ip:
            info_result, _info_reason, profile = call_backend_info(username, nas_ip)
            if info_result == RESULT_OK and profile is not None:
                req[AV_TACPROFILE] = profile
    elif tactype == "INFO":
        username = req.get(AV_USER, "")
        nas_ip = req.get(AV_SERVERIP, "")
        result, _reason, profile = call_backend_info(username, nas_ip)
        req[AV_RESULT] = result
        if result == RESULT_OK and profile is not None:
            req[AV_TACPROFILE] = profile
    elif tactype == "CHPW":
        # Change-password isn't wired up yet; the daemon falls back without
        # a profile when MAVIS says fail.
        req[AV_RESULT] = RESULT_FAIL
    elif tactype == "HOST":
        # NAS hosts are still declared statically in tac_plus-ng.cfg; the
        # NAS-config-regen flow that replaces this lands later in M4.
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
