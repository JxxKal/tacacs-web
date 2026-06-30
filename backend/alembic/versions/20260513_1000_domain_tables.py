"""domain tables: device_group, privilege_profile, device, authorization

Revision ID: 20260513_1000
Revises: 20260512_1700
Create Date: 2026-05-13

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260513_1000"
down_revision: str | None = "20260512_1700"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "device_group",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("name", name="device_group_name_key"),
    )

    op.create_table(
        "privilege_profile",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("tacacs_priv_lvl", sa.Integer(), nullable=False),
        sa.Column(
            "permit_commands_regex", sa.JSON(), nullable=False, server_default=sa.text("'[]'")
        ),
        sa.Column("deny_commands_regex", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("extra_av_pairs", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("name", name="privilege_profile_name_key"),
        sa.CheckConstraint(
            "tacacs_priv_lvl >= 0 AND tacacs_priv_lvl <= 15",
            name="privilege_profile_priv_lvl_range",
        ),
    )

    op.create_table(
        "device",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("ip_or_cidr", sa.String(64), nullable=False),
        sa.Column(
            "device_group_id",
            sa.Integer(),
            sa.ForeignKey("device_group.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("current_secret_enc", sa.String(), nullable=True),
        sa.Column("previous_secret_enc", sa.String(), nullable=True),
        sa.Column("previous_retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
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
        sa.UniqueConstraint("name", name="device_name_key"),
        sa.UniqueConstraint("ip_or_cidr", name="device_ip_or_cidr_key"),
    )
    op.create_index("ix_device_device_group_id", "device", ["device_group_id"])

    op.create_table(
        "authorization",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "principal_user_id",
            sa.Integer(),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "principal_ad_group_id",
            sa.Integer(),
            sa.ForeignKey("ad_group.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "device_group_id",
            sa.Integer(),
            sa.ForeignKey("device_group.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "privilege_profile_id",
            sa.Integer(),
            sa.ForeignKey("privilege_profile.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "(principal_user_id IS NOT NULL AND principal_ad_group_id IS NULL)"
            " OR (principal_user_id IS NULL AND principal_ad_group_id IS NOT NULL)",
            name="authorization_exactly_one_principal",
        ),
        sa.UniqueConstraint(
            "principal_user_id",
            "device_group_id",
            "privilege_profile_id",
            name="authorization_unique_user_dg_profile",
        ),
        sa.UniqueConstraint(
            "principal_ad_group_id",
            "device_group_id",
            "privilege_profile_id",
            name="authorization_unique_adgroup_dg_profile",
        ),
    )
    op.create_index("ix_authorization_principal_user_id", "authorization", ["principal_user_id"])
    op.create_index(
        "ix_authorization_principal_ad_group_id", "authorization", ["principal_ad_group_id"]
    )
    op.create_index("ix_authorization_device_group_id", "authorization", ["device_group_id"])
    op.create_index(
        "ix_authorization_privilege_profile_id", "authorization", ["privilege_profile_id"]
    )
    op.create_index(
        "authorization_lookup_user",
        "authorization",
        ["principal_user_id", "device_group_id"],
    )
    op.create_index(
        "authorization_lookup_adgroup",
        "authorization",
        ["principal_ad_group_id", "device_group_id"],
    )


def downgrade() -> None:
    op.drop_index("authorization_lookup_adgroup", table_name="authorization")
    op.drop_index("authorization_lookup_user", table_name="authorization")
    op.drop_index("ix_authorization_privilege_profile_id", table_name="authorization")
    op.drop_index("ix_authorization_device_group_id", table_name="authorization")
    op.drop_index("ix_authorization_principal_ad_group_id", table_name="authorization")
    op.drop_index("ix_authorization_principal_user_id", table_name="authorization")
    op.drop_table("authorization")
    op.drop_index("ix_device_device_group_id", table_name="device")
    op.drop_table("device")
    op.drop_table("privilege_profile")
    op.drop_table("device_group")
