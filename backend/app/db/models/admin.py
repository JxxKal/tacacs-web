"""Local break-glass admin + server-side web sessions + audit log.

ADR-0003: exactly one local admin row; managed via the `tacacs-web
bootstrap-admin` CLI. UI cannot create, list, or delete. Used when the
SAML IdP is unreachable.

ADR-0009: audit log is append-only (no UPDATE/DELETE path in code) and
action-only (no before/after JSON columns). 365d retention by default.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class LocalAdmin(Base):
    """The one and only local admin. Schema enforces single-row via id == 1.

    Operators rotate the password via `tacacs-web bootstrap-admin
    --reset-password`. No "list admins" path; no "delete admin" path.
    """

    __tablename__ = "local_admin"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_argon2_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    allowed_source_cidr: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("id = 1", name="local_admin_singleton"),
    )


class WebSession(Base):
    """Server-side session for the admin UI.

    Token is a cryptographically-random URL-safe string stored as the
    primary key — we look up by cookie value directly. Sliding expiration
    is maintained by bumping `expires_at` on every authenticated request,
    capped by `hard_expires_at` (24h cap per ADR-0003).
    """

    __tablename__ = "web_session"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    auth_method: Mapped[str] = mapped_column(String(16), nullable=False)
    local_admin_id: Mapped[int | None] = mapped_column(
        ForeignKey("local_admin.id", ondelete="CASCADE")
    )
    username_snapshot: Mapped[str] = mapped_column(String(256), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    hard_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    client_ip: Mapped[str | None] = mapped_column(String(64))

    __table_args__ = (
        CheckConstraint(
            "auth_method IN ('local', 'saml')",
            name="web_session_auth_method_valid",
        ),
    )


class AuditLog(Base):
    """Append-only audit log (ADR-0009).

    Application code MUST NOT issue UPDATE or DELETE against this table
    outside the retention-pruning job. No FK to local_admin / user — we
    keep `actor_username_snapshot` so rows survive principal deletion.
    `action` is a closed vocabulary defined in `app.audit.actions`.
    """

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    actor_id: Mapped[int | None] = mapped_column(Integer)
    actor_username_snapshot: Mapped[str] = mapped_column(String(256), nullable=False)
    actor_role: Mapped[str] = mapped_column(String(16), nullable=False)
    auth_method: Mapped[str] = mapped_column(String(16), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(64))
    target_id: Mapped[int | None] = mapped_column(Integer)
    summary: Mapped[str | None] = mapped_column(Text)
    client_ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(512))

    __table_args__ = (
        Index("ix_audit_log_ts", "ts"),
        Index("ix_audit_log_action", "action"),
        Index("ix_audit_log_actor_username_snapshot", "actor_username_snapshot"),
    )
