"""durable document_blobs table (survive ephemeral-disk wipes)

Revision ID: a1c4e7f09b23
Revises: 7f3a1c9d2b54
Create Date: 2026-10-04
"""
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import LONGBLOB

revision: str = "a1c4e7f09b23"
down_revision: Union[str, None] = "7f3a1c9d2b54"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def _has_blobs_table() -> bool:
    """MySQL auto-commits DDL, so an interrupted upgrade can leave the table
    created while alembic_version still points at the previous revision. Make
    the upgrade idempotent so re-running it on a drifted database is safe
    instead of crashing every later startup."""
    insp = sa.inspect(op.get_bind())
    return "document_blobs" in insp.get_table_names()


def upgrade() -> None:
    if _has_blobs_table():
        return
    op.create_table(
        "document_blobs",
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("data", LONGBLOB(), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"], ["documents.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("document_id"),
    )


def downgrade() -> None:
    if not _has_blobs_table():
        return
    op.drop_table("document_blobs")
