"""Secret resolution in `Settings`: file path vs. direct env value.

Both `master_key` and the DB password can come from a mounted file (the
Docker-secret / bind-mount path) or straight from an env var (the
Portainer / plain-env path). A present file always wins so the value
stays off the process environment.
"""

from __future__ import annotations

import base64

import pytest

from app.core.config import Settings


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode()


def test_master_key_from_env_value() -> None:
    s = Settings()
    s.master_key_file = None
    s.master_key_b64 = _b64(b"k" * 32)
    assert s.master_key_configured() is True
    assert s.master_key() == b"k" * 32


def test_master_key_file_wins_over_env(tmp_path) -> None:
    key_file = tmp_path / "master.key"
    key_file.write_bytes(base64.b64encode(b"f" * 32))
    s = Settings()
    s.master_key_file = key_file
    s.master_key_b64 = _b64(b"e" * 32)
    assert s.master_key() == b"f" * 32


def test_master_key_unconfigured_raises() -> None:
    s = Settings()
    s.master_key_file = None
    s.master_key_b64 = None
    assert s.master_key_configured() is False
    with pytest.raises(RuntimeError):
        s.master_key()


def test_master_key_env_wrong_length_raises() -> None:
    s = Settings()
    s.master_key_file = None
    s.master_key_b64 = _b64(b"too-short")
    with pytest.raises(ValueError):
        s.master_key()


def test_database_password_env_and_file_precedence(tmp_path) -> None:
    s = Settings()
    s.database_password_file = None
    s.database_password_value = "env-pw"
    assert s.database_password() == "env-pw"

    pw_file = tmp_path / "pw"
    pw_file.write_text("file-pw\n")
    s.database_password_file = pw_file
    assert s.database_password() == "file-pw"  # file wins, trailing newline stripped


def test_database_password_unset_is_none() -> None:
    s = Settings()
    s.database_password_file = None
    s.database_password_value = None
    assert s.database_password() is None
