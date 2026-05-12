"""Pytest setup: seed minimal env so `app.core.config.settings` constructs
without requiring real secrets, then expose a sync TestClient fixture.
"""

from __future__ import annotations

import base64
import os
import secrets as _secrets
import tempfile
from pathlib import Path

# Provide a tmp master-key file in the same shape an operator gets from
# `openssl rand -base64 32 > master.key` — base64 of 32 random bytes plus
# a trailing newline. Mirrors the documented bootstrap procedure.
_TMP = Path(tempfile.mkdtemp(prefix="tacacs-web-tests-"))
_MASTER_KEY = _TMP / "master.key"
_MASTER_KEY.write_bytes(base64.b64encode(_secrets.token_bytes(32)) + b"\n")

os.environ.setdefault("MASTER_KEY_FILE", str(_MASTER_KEY))
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://nobody@127.0.0.1:1/tacacs_test")
os.environ.setdefault("LOG_LEVEL", "WARNING")
