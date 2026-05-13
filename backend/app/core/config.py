"""Application settings loaded from environment variables and Docker secrets.

See ADR-0004 for the master-key/secrets model.
"""

from __future__ import annotations

import base64
from pathlib import Path

from pydantic import Field
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
    master_key_file: Path | None = Field(
        default=None,
        description="Path to the AES-GCM master key file. 32 raw bytes or base64-encoded. "
        "Production startup is gated on this being readable (M3+).",
    )
    base_url: str = Field(default="https://localhost:8443")
    log_level: str = Field(default="INFO")
    session_cookie_secure: bool = Field(
        default=True,
        description="Set Secure flag on the session cookie. Disable only for "
        "HTTP-only test setups; production reverse proxy always serves HTTPS.",
    )

    def database_password(self) -> str | None:
        if self.database_password_file is None:
            return None
        return self.database_password_file.read_text().strip()

    def master_key(self) -> bytes:
        if self.master_key_file is None:
            raise RuntimeError("master_key_file is not configured")
        raw = self.master_key_file.read_bytes()
        if len(raw) == 32:
            return raw
        decoded = base64.b64decode(raw.strip())
        if len(decoded) != 32:
            raise ValueError("master_key_file must contain 32 bytes (raw or base64-encoded)")
        return decoded


settings = Settings()
