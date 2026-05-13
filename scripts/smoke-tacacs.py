#!/usr/bin/env python3
"""End-to-end smoke test for the TACACS+ stack.

Connects to a running `tac_plus-ng` instance and exercises one of two flows:

- `STEP=AUTHN` (default) — sends an authentication request and asserts
  ACCEPT or REJECT per `EXPECT`. Used to validate the live-LDAPS-bind path
  through MAVIS AUTH.
- `STEP=AUTHZ` — sends an authorisation request (`service=shell`, empty cmd)
  and asserts the daemon returns ACCEPT with a `priv-lvl` AV matching
  `EXPECT_PRIV_LVL`. Used to validate the MAVIS INFO path that renders the
  effective PrivilegeProfile.

Reproducible locally:

    pip install tacacs_plus
    TACACS_SHARED_SECRET=smoketest-shared-secret \\
      docker compose -f docker/compose.yml --profile integration up -d --wait \\
      db backend openldap tac_plus-ng
    psql ... < scripts/seed-integration.sql
    TACACS_SECRET=smoketest-shared-secret STEP=AUTHN  ./scripts/smoke-tacacs.py
    TACACS_SECRET=smoketest-shared-secret STEP=AUTHZ EXPECT_PRIV_LVL=15 \\
      ./scripts/smoke-tacacs.py
"""

from __future__ import annotations

import os
import socket
import sys
import time
from collections.abc import Callable
from typing import TypeVar

from tacacs_plus.client import TACACSClient

T = TypeVar("T")


def wait_for_port(host: str, port: int, deadline_s: float = 60.0) -> None:
    end = time.monotonic() + deadline_s
    last_exc: Exception | None = None
    while time.monotonic() < end:
        try:
            with socket.create_connection((host, port), timeout=2):
                return
        except OSError as exc:
            last_exc = exc
            time.sleep(2)
    raise TimeoutError(
        f"port {host}:{port} did not accept connections within {deadline_s:.0f}s "
        f"(last error: {last_exc!r})"
    )


def retry_transient(fn: Callable[[], T], *, deadline_s: float = 60.0) -> T:
    """Re-invoke `fn` until it returns without a transient socket error.

    Docker's userland proxy accepts a TCP connection even before the daemon
    inside the container is ready, then resets the stream. Retry until the
    daemon is actually serving (or the deadline expires).
    """
    deadline = time.monotonic() + deadline_s
    last_exc: Exception | None = None
    while time.monotonic() < deadline:
        try:
            return fn()
        except (ConnectionResetError, ConnectionRefusedError, OSError) as exc:
            last_exc = exc
            print(f"... transient: {exc.__class__.__name__}: {exc}; retrying", file=sys.stderr)
            time.sleep(2)
    raise RuntimeError(f"call kept failing for {deadline_s:.0f}s (last={last_exc!r})")


def run_authn(client: TACACSClient, user: str, password: str, expect: str) -> int:
    print(f"... TACACS+ authn user={user!r} (expect={expect})")
    result = retry_transient(lambda: client.authenticate(user, password))

    if expect == "ACCEPT":
        if not result.valid:
            print(f"FAIL: expected ACCEPT but got status={result.status!r}", file=sys.stderr)
            return 2
        print(f"OK: authn accepted user={user!r} status={result.status!r}")
        return 0

    if result.valid:
        print(f"FAIL: expected REJECT but got status={result.status!r}", file=sys.stderr)
        return 3
    print(f"OK: authn rejected user={user!r} status={result.status!r}")
    return 0


def run_authz(client: TACACSClient, user: str, expect_priv_lvl: int) -> int:
    print(f"... TACACS+ authz user={user!r} expect priv-lvl={expect_priv_lvl}")
    # service=shell, empty cmd -> initial shell-session authz request, the
    # one the daemon's profile script handles with `if (cmd == "") set priv-lvl`.
    arguments = [b"service=shell", b"cmd="]
    result = retry_transient(lambda: client.authorize(user, arguments=arguments))

    if not result.valid:
        print(
            f"FAIL: authz did not return ACCEPT; status={result.status!r} "
            f"arguments={result.arguments!r}",
            file=sys.stderr,
        )
        return 4

    av_pairs = {
        kv.split(b"=", 1)[0].decode(): kv.split(b"=", 1)[1].decode()
        for kv in (result.arguments or [])
        if b"=" in kv
    }
    actual = av_pairs.get("priv-lvl")
    if actual != str(expect_priv_lvl):
        print(
            f"FAIL: priv-lvl mismatch: expected {expect_priv_lvl}, got {actual!r}; "
            f"all AVs: {av_pairs!r}",
            file=sys.stderr,
        )
        return 5

    print(f"OK: authz returned priv-lvl={actual} for user={user!r}")
    return 0


def main() -> int:
    host = os.environ.get("TACACS_HOST", "127.0.0.1")
    port = int(os.environ.get("TACACS_PORT", "49"))
    secret = os.environ.get("TACACS_SECRET", "smoketest-shared-secret")
    user = os.environ.get("TACACS_USER", "smokeuser")
    step = os.environ.get("STEP", "AUTHN").upper()

    print(f"... waiting for {host}:{port}")
    wait_for_port(host, port, deadline_s=60.0)
    client = TACACSClient(host, port, secret, timeout=10)

    if step == "AUTHN":
        password = os.environ.get("TACACS_PASSWORD", "anypass")
        expect = os.environ.get("EXPECT", "ACCEPT").upper()
        if expect not in {"ACCEPT", "REJECT"}:
            print(f"FAIL: EXPECT must be ACCEPT or REJECT, got {expect!r}", file=sys.stderr)
            return 64
        return run_authn(client, user, password, expect)

    if step == "AUTHZ":
        expect_priv_lvl = int(os.environ.get("EXPECT_PRIV_LVL", "15"))
        return run_authz(client, user, expect_priv_lvl)

    print(f"FAIL: STEP must be AUTHN or AUTHZ, got {step!r}", file=sys.stderr)
    return 64


if __name__ == "__main__":
    sys.exit(main())
