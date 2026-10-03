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


def _has_instruction_column() -> bool:
    """MySQL auto-commits DDL, so an interrupted upgrade can leave the column
    added while alembic_version still points at the previous revision. Make
    the upgrade idempotent so re-running it on a drifted database is safe
    instead of crashing every later startup."""
    insp = sa.inspect(op.get_bind())
    if "redlines" not in insp.get_table_names():
        return False
    return any(c["name"] == "instruction" for c in insp.get_columns("redlines"))


def upgrade() -> None:
    if _has_instruction_column():
        return
    op.add_column(
        "redlines",
        sa.Column("instruction", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    if not _has_instruction_column():
        return
    op.drop_column("redlines", "instruction")
