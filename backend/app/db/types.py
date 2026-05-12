"""Custom SQLAlchemy column types."""

from __future__ import annotations

from typing import Any

from sqlalchemy import String
from sqlalchemy.types import TypeDecorator

from app.core.config import settings
from app.core.crypto import decrypt, encrypt


class EncryptedStr(TypeDecorator[str]):
    """TEXT column that transparently encrypts with the master key (ADR-0004)."""

    impl = String
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect: Any) -> str | None:
        if value is None:
            return None
        return encrypt(value, settings.master_key())

    def process_result_value(self, value: str | None, dialect: Any) -> str | None:
        if value is None:
            return None
        return decrypt(value, settings.master_key())
