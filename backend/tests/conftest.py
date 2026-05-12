"""Pytest setup: seed minimal env so `app.core.config.settings` constructs
without requiring real secrets, then expose a sync TestClient fixture.
"""

from __future__ import annotations

import os
import secrets as _secrets
import tempfile
from pathlib import Path

# Provide a tmp master-key file for tests that exercise ready-checks.
_TMP = Path(tempfile.mkdtemp(prefix="tacacs-web-tests-"))
_MASTER_KEY = _TMP / "master.key"
_MASTER_KEY.write_bytes(_secrets.token_bytes(32))

os.environ.setdefault("MASTER_KEY_FILE", str(_MASTER_KEY))
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://nobody@127.0.0.1:1/tacacs_test")
os.environ.setdefault("LOG_LEVEL", "WARNING")
