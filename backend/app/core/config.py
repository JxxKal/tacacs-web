"""Application settings loaded from environment variables and Docker secrets.

See ADR-0004 for the master-key/secrets model.
"""

from __future__ import annotations

import base64
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_file=None,
    )

    database_url: str = Field(
        default="postgresql+psycopg://tacacs@db:5432/tacacs",
        description="SQLAlchemy async URL. Password is injected at engine-build time "
        "from `database_password_file` if set.",
    )
    database_password_file: Path | None = Field(
        default=None,
        description="Path to a file containing the DB password (Docker secret mount).",
    )
    database_password_value: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DATABASE_PASSWORD", "database_password_value"),
        description="DB password supplied directly via env. Used when no "
        "`database_password_file` is set — the Portainer / plain-env path.",
    )
    master_key_file: Path | None = Field(
        default=None,
        description="Path to the AES-GCM master key file. 32 raw bytes or base64-encoded. "
        "Production startup is gated on this being readable (M3+).",
    )
    master_key_b64: str | None = Field(
        default=None,
        validation_alias=AliasChoices("MASTER_KEY", "master_key_b64"),
        description="AES-GCM master key as a base64 string, supplied directly via "
        "env. Used when no `master_key_file` is set — the Portainer / plain-env "
        "path. Less private than a file mount (visible in `docker inspect`); see "
        "ADR-0004 and DEPLOY.md for the tradeoff.",
    )
    base_url: str = Field(default="https://localhost:8443")
    log_level: str = Field(default="INFO")
    session_cookie_secure: bool = Field(
        default=True,
        description="Set Secure flag on the session cookie. Disable only for "
        "HTTP-only test setups; production reverse proxy always serves HTTPS.",
    )

    def database_password(self) -> str | None:
        # A mounted file wins over the env value so a Docker-secret / bind-mount
        # deployment keeps the password off the process environment.
        if self.database_password_file is not None:
            return self.database_password_file.read_text().strip()
        return self.database_password_value

    def master_key_configured(self) -> bool:
        """True if a master key is available via either the file or env path."""
        return self.master_key_file is not None or self.master_key_b64 is not None

    def master_key(self) -> bytes:
        # File path first (preferred), env value second. The 32-raw-bytes check
        # must run before `.strip()` so a key whose bytes happen to be
        # whitespace isn't silently mangled (see the crypto strip-ordering rule).
        if self.master_key_file is not None:
            raw = self.master_key_file.read_bytes()
            if len(raw) == 32:
                return raw
            decoded = base64.b64decode(raw.strip())
            if len(decoded) != 32:
                raise ValueError("master_key_file must contain 32 bytes (raw or base64-encoded)")
            return decoded
        if self.master_key_b64 is not None:
            decoded = base64.b64decode(self.master_key_b64.strip())
            if len(decoded) != 32:
                raise ValueError("MASTER_KEY must decode to 32 bytes (base64-encoded)")
            return decoded
        raise RuntimeError("master key is not configured (set MASTER_KEY or master_key_file)")


settings = Settings()
