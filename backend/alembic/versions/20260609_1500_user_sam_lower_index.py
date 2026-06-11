"""case-insensitive uniqueness + lookup index on user.sam_account_name

The MAVIS auth/info lookups match the username the NAS forwards against
`sam_account_name`. AD is case-insensitive but stores the casing as created
(e.g. `SSCHNACK.OT`), while end users type their name lowercase. A functional
`lower(sam_account_name)` unique index lets the lookup compare case-insensitively
*and* prevents two AD objects differing only by case from colliding.

Revision ID: 20260609_1500
Revises: 20260520_1700
Create Date: 2026-06-09

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260609_1500"
down_revision: str | None = "20260520_1700"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "uq_user_sam_account_name_lower",
        "user",
        [sa.text("lower(sam_account_name)")],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_user_sam_account_name_lower", table_name="user")
