#!/usr/bin/env python3
"""End-to-end smoke test for the TACACS+ stack.

Connects to a running `tac_plus-ng` instance, sends a single authentication
request with the configured shared secret, and exits non-zero if the
daemon doesn't ACCEPT.

Used by the integration workflow and reproducible locally:

    pip install tacacs_plus
    TACACS_SHARED_SECRET=smoketest-shared-secret \\
      docker compose -f docker/compose.yml up -d --wait db backend tac_plus-ng
    TACACS_SECRET=smoketest-shared-secret ./scripts/smoke-tacacs.py
"""

from __future__ import annotations

import os
import socket
import sys
import time

from tacacs_plus.client import TACACSClient


def wait_for_port(host: str, port: int, deadline_s: float = 60.0) -> None:
    """Poll until a TCP connect succeeds or we run out of time."""
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


def main() -> int:
    host = os.environ.get("TACACS_HOST", "127.0.0.1")
    port = int(os.environ.get("TACACS_PORT", "49"))
    secret = os.environ.get("TACACS_SECRET", "smoketest-shared-secret")
    user = os.environ.get("TACACS_USER", "smokeuser")
    password = os.environ.get("TACACS_PASSWORD", "anypass")
    expect = os.environ.get("EXPECT", "ACCEPT").upper()
    if expect not in {"ACCEPT", "REJECT"}:
        print(f"FAIL: EXPECT must be ACCEPT or REJECT, got {expect!r}", file=sys.stderr)
        return 64

    print(f"... waiting for {host}:{port}")
    wait_for_port(host, port, deadline_s=60.0)
    print(f"... connected; trying TACACS+ authn for user={user!r} (expect={expect})")

    # Docker's userland proxy accepts a TCP connection even before the
    # daemon inside the container is ready, then resets the stream once
    # the backend isn't reachable. Retry the auth until the daemon is
    # actually serving.
    client = TACACSClient(host, port, secret, timeout=10)
    deadline = time.monotonic() + 60.0
    last_exc: Exception | None = None
    while time.monotonic() < deadline:
        try:
            result = client.authenticate(user, password)
            break
        except (ConnectionResetError, ConnectionRefusedError, OSError) as exc:
            last_exc = exc
            print(f"... transient: {exc.__class__.__name__}: {exc}; retrying", file=sys.stderr)
            time.sleep(2)
    else:
        print(
            f"FAIL: authenticate kept failing for 60s (last error: {last_exc!r})",
            file=sys.stderr,
        )
        return 1

    if expect == "ACCEPT":
        if not result.valid:
            print(
                f"FAIL: expected ACCEPT but got status={result.status!r}",
                file=sys.stderr,
            )
            return 2
        print(f"OK: TACACS+ authn accepted user={user!r} status={result.status!r}")
        return 0

    # expect == REJECT
    if result.valid:
        print(
            f"FAIL: expected REJECT but got status={result.status!r}",
            file=sys.stderr,
        )
        return 3
    print(f"OK: TACACS+ authn rejected user={user!r} status={result.status!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
