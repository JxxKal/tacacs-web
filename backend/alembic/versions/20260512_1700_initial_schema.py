"""initial schema: system_setting, system_secret, user, ad_group, user_ad_group

Revision ID: 20260512_1700
Revises:
Create Date: 2026-05-12

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260512_1700"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "system_setting",
        sa.Column("key", sa.String(128), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_table(
        "system_secret",
        sa.Column("key", sa.String(128), primary_key=True),
        sa.Column("value", sa.String(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        "user",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sam_account_name", sa.String(256), nullable=False),
        sa.Column("ad_object_guid", sa.String(36), nullable=True),
        sa.Column("distinguished_name", sa.String(1024), nullable=False),
        sa.Column("upn", sa.String(256), nullable=True),
        sa.Column("display_name", sa.String(256), nullable=True),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("last_seen_in_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_user_sam_account_name", "user", ["sam_account_name"], unique=True)
    op.create_index("ix_user_ad_object_guid", "user", ["ad_object_guid"], unique=True)

    op.create_table(
        "ad_group",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sid", sa.String(64), nullable=False),
        sa.Column("distinguished_name", sa.String(1024), nullable=False),
        sa.Column("name", sa.String(256), nullable=True),
        sa.Column("last_seen_in_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_ad_group_sid", "ad_group", ["sid"], unique=True)

    op.create_table(
        "user_ad_group",
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "ad_group_id",
            sa.Integer(),
            sa.ForeignKey("ad_group.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )


def downgrade() -> None:
    op.drop_table("user_ad_group")
    op.drop_index("ix_ad_group_sid", table_name="ad_group")
    op.drop_table("ad_group")
    op.drop_index("ix_user_ad_object_guid", table_name="user")
    op.drop_index("ix_user_sam_account_name", table_name="user")
    op.drop_table("user")
    op.drop_table("system_secret")
    op.drop_table("system_setting")
