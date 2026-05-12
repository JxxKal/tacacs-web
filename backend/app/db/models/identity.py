"""AD-synced identity tables: users, groups, and their join.

See ADR-0002 (hybrid AD model). `last_seen_in_sync_at` tracks when the sync
worker last saw the entity; users that fall out of scope keep their row but
get `enabled=false`.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(primary_key=True)
    sam_account_name: Mapped[str] = mapped_column(String(256), unique=True, index=True)
    ad_object_guid: Mapped[str | None] = mapped_column(String(36), unique=True, index=True)
    distinguished_name: Mapped[str] = mapped_column(String(1024), nullable=False)
    upn: Mapped[str | None] = mapped_column(String(256))
    display_name: Mapped[str | None] = mapped_column(String(256))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_seen_in_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    groups: Mapped[list[ADGroup]] = relationship(secondary="user_ad_group", back_populates="users")


class ADGroup(Base):
    __tablename__ = "ad_group"

    id: Mapped[int] = mapped_column(primary_key=True)
    sid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    distinguished_name: Mapped[str] = mapped_column(String(1024), nullable=False)
    name: Mapped[str | None] = mapped_column(String(256))
    last_seen_in_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    users: Mapped[list[User]] = relationship(secondary="user_ad_group", back_populates="groups")


class UserADGroup(Base):
    __tablename__ = "user_ad_group"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), primary_key=True
    )
    ad_group_id: Mapped[int] = mapped_column(
        ForeignKey("ad_group.id", ondelete="CASCADE"), primary_key=True
    )
