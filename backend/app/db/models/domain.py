"""Domain tables: devices, device groups, privilege profiles, authorizations.

See ADR-0005 (flat device groups, 1:1 device-to-group) and ADR-0006 (permissive
authz conflict resolution; direct-user override).

`authorization` carries a polymorphic principal modeled as two nullable FKs
(`principal_user_id` / `principal_ad_group_id`) plus a CHECK constraint that
exactly one is set. Cleaner queries than a single nullable + type column.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import EncryptedStr

if TYPE_CHECKING:
    pass


def _utcnow() -> datetime:
    return datetime.now(UTC)


class DeviceGroup(Base):
    __tablename__ = "device_group"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    devices: Mapped[list[Device]] = relationship(back_populates="device_group")


class PrivilegeProfile(Base):
    """Global, reusable bundle of TACACS+ authorization attributes.

    Service is implicitly `shell` (v1 out-of-scope: junos-exec, ppp, …).
    `permit_commands_regex` / `deny_commands_regex` are PCRE2 patterns;
    deny wins over permit per ADR-0006 (and how tac_plus-ng evaluates
    profile scripts). `extra_av_pairs` is a flat string->string map of
    additional AV-pairs to set on the shell session.
    """

    __tablename__ = "privilege_profile"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    tacacs_priv_lvl: Mapped[int] = mapped_column(Integer, nullable=False)
    permit_commands_regex: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    deny_commands_regex: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    extra_av_pairs: Mapped[dict[str, str]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "tacacs_priv_lvl >= 0 AND tacacs_priv_lvl <= 15",
            name="privilege_profile_priv_lvl_range",
        ),
    )


class Device(Base):
    """A single network device (NAS).

    `ip_or_cidr` stores either a host address ("192.0.2.10") or a CIDR block
    ("10.0.0.0/24"). The runtime resolves the NAS source IP to a Device via
    longest-prefix match in Python (devices are O(thousands); no Postgres
    inet/cidr typing is required, keeping SQLite-based unit tests trivial).

    Shared-secret rotation: `current_secret_enc` is mandatory once set;
    `previous_secret_enc` is filled during a rotation window (ADR-0007). The
    `host` block rendered into tac_plus-ng.cfg lists both, separated.
    """

    __tablename__ = "device"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    ip_or_cidr: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    device_group_id: Mapped[int] = mapped_column(
        ForeignKey("device_group.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    current_secret_enc: Mapped[str | None] = mapped_column(EncryptedStr())
    previous_secret_enc: Mapped[str | None] = mapped_column(EncryptedStr())
    previous_retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    device_group: Mapped[DeviceGroup] = relationship(back_populates="devices")


class Authorization(Base):
    """Edge from a principal (User OR ADGroup) to a (DeviceGroup, PrivilegeProfile).

    Exactly one of `principal_user_id` / `principal_ad_group_id` is set,
    enforced via CHECK constraint. `is_direct` is a derived view for code
    readability — `True` iff principal_user_id is set. ADR-0006 says direct-
    user overrides AD-group at conflict-resolution time; we expose that
    intent in the property.
    """

    __tablename__ = "authorization"

    id: Mapped[int] = mapped_column(primary_key=True)
    principal_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), index=True
    )
    principal_ad_group_id: Mapped[int | None] = mapped_column(
        ForeignKey("ad_group.id", ondelete="CASCADE"), index=True
    )
    device_group_id: Mapped[int] = mapped_column(
        ForeignKey("device_group.id", ondelete="CASCADE"), nullable=False, index=True
    )
    privilege_profile_id: Mapped[int] = mapped_column(
        ForeignKey("privilege_profile.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    privilege_profile: Mapped[PrivilegeProfile] = relationship(lazy="joined")
    device_group: Mapped[DeviceGroup] = relationship(lazy="joined")

    __table_args__ = (
        CheckConstraint(
            "(principal_user_id IS NOT NULL AND principal_ad_group_id IS NULL)"
            " OR (principal_user_id IS NULL AND principal_ad_group_id IS NOT NULL)",
            name="authorization_exactly_one_principal",
        ),
        # No partial unique on (principal_user_id, device_group_id) here:
        # we allow multiple rows per (user, device_group) and resolve them
        # at runtime per ADR-0006. Same for AD-group.
        UniqueConstraint(
            "principal_user_id",
            "device_group_id",
            "privilege_profile_id",
            name="authorization_unique_user_dg_profile",
        ),
        UniqueConstraint(
            "principal_ad_group_id",
            "device_group_id",
            "privilege_profile_id",
            name="authorization_unique_adgroup_dg_profile",
        ),
        Index(
            "authorization_lookup_user",
            "principal_user_id",
            "device_group_id",
        ),
        Index(
            "authorization_lookup_adgroup",
            "principal_ad_group_id",
            "device_group_id",
        ),
    )

    @property
    def is_direct(self) -> bool:
        return self.principal_user_id is not None
