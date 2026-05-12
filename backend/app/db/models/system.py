"""System-wide configuration tables.

Two tables for clarity: `system_setting` (plaintext, e.g. base DNs, LDAP URL,
sync cadence) and `system_secret` (encrypted-at-rest with the AES-GCM master
key, e.g. AD bind password, SAML signing key).
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import EncryptedStr


def _utcnow() -> datetime:
    return datetime.now(UTC)


class SystemSetting(Base):
    __tablename__ = "system_setting"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
    )


class SystemSecret(Base):
    __tablename__ = "system_secret"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(EncryptedStr(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
    )
