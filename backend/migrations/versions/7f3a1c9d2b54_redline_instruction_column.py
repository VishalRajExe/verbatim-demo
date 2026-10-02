"""redline sessions carry the plain-English instruction (nullable)

Revision ID: 7f3a1c9d2b54
Revises: 224bfb93426d
Create Date: 2026-10-03
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "7f3a1c9d2b54"
down_revision: Union[str, None] = "224bfb93426d"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.add_column(
        "redlines",
        sa.Column("instruction", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("redlines", "instruction")
