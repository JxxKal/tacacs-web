"""accounting_record table for M6 accounting ingestor

Revision ID: 20260520_1700
Revises: 20260513_1500
Create Date: 2026-05-20

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260520_1700"
down_revision: str | None = "20260513_1500"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "accounting_record",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "ts",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("nas_ip", sa.String(64), nullable=True),
        sa.Column("username", sa.String(256), nullable=True),
        sa.Column("port", sa.String(64), nullable=True),
        sa.Column("nac_ip", sa.String(64), nullable=True),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("service", sa.String(32), nullable=True),
        sa.Column("cmd", sa.Text(), nullable=True),
        sa.Column("priv_lvl", sa.Integer(), nullable=True),
        sa.Column("elapsed_seconds", sa.Integer(), nullable=True),
        sa.Column("task_id", sa.String(64), nullable=True),
        sa.Column(
            "device_id",
            sa.Integer(),
            sa.ForeignKey("device.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "raw_av_pairs",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    op.create_index("ix_accounting_record_ts", "accounting_record", ["ts"])
    op.create_index(
        "ix_accounting_record_username", "accounting_record", ["username"]
    )
    op.create_index("ix_accounting_record_nas_ip", "accounting_record", ["nas_ip"])
    op.create_index("ix_accounting_record_task_id", "accounting_record", ["task_id"])
    op.create_index("ix_accounting_record_action", "accounting_record", ["action"])


def downgrade() -> None:
    op.drop_index("ix_accounting_record_action", table_name="accounting_record")
    op.drop_index("ix_accounting_record_task_id", table_name="accounting_record")
    op.drop_index("ix_accounting_record_nas_ip", table_name="accounting_record")
    op.drop_index("ix_accounting_record_username", table_name="accounting_record")
    op.drop_index("ix_accounting_record_ts", table_name="accounting_record")
    op.drop_table("accounting_record")
