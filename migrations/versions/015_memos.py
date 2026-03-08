"""Memo drafting table.

Adds ``memos`` table for persisting generated legal memos.

Revision ID: 015
Revises: 9104d926aca7
Create Date: 2026-03-08 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "015"
down_revision: str | None = "9104d926aca7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "memos",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("matter_id", sa.UUID(), sa.ForeignKey("case_matters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("thread_id", sa.String(255), nullable=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("sections", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("format", sa.String(20), nullable=False, server_default="markdown"),
        sa.Column("created_by", sa.UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_memos_matter_id", "memos", ["matter_id"])


def downgrade() -> None:
    op.drop_table("memos")
