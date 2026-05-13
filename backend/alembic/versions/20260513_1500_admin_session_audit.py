"""local_admin + web_session + audit_log

Revision ID: 20260513_1500
Revises: 20260513_1000
Create Date: 2026-05-13

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260513_1500"
down_revision: str | None = "20260513_1000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "local_admin",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("password_argon2_hash", sa.String(512), nullable=False),
        sa.Column("allowed_source_cidr", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("username", name="local_admin_username_key"),
        sa.CheckConstraint("id = 1", name="local_admin_singleton"),
    )

    op.create_table(
        "web_session",
        sa.Column("token", sa.String(64), primary_key=True),
        sa.Column("auth_method", sa.String(16), nullable=False),
        sa.Column(
            "local_admin_id",
            sa.Integer(),
            sa.ForeignKey("local_admin.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("username_snapshot", sa.String(256), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("hard_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("client_ip", sa.String(64), nullable=True),
        sa.CheckConstraint(
            "auth_method IN ('local', 'saml')",
            name="web_session_auth_method_valid",
        ),
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "ts",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("actor_username_snapshot", sa.String(256), nullable=False),
        sa.Column("actor_role", sa.String(16), nullable=False),
        sa.Column("auth_method", sa.String(16), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target_type", sa.String(64), nullable=True),
        sa.Column("target_id", sa.Integer(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("client_ip", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.String(512), nullable=True),
    )
    op.create_index("ix_audit_log_ts", "audit_log", ["ts"])
    op.create_index("ix_audit_log_action", "audit_log", ["action"])
    op.create_index(
        "ix_audit_log_actor_username_snapshot",
        "audit_log",
        ["actor_username_snapshot"],
    )


def downgrade() -> None:
    op.drop_index("ix_audit_log_actor_username_snapshot", table_name="audit_log")
    op.drop_index("ix_audit_log_action", table_name="audit_log")
    op.drop_index("ix_audit_log_ts", table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_table("web_session")
    op.drop_table("local_admin")
