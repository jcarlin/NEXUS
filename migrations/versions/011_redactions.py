"""Redactions table and redacted_pdf_path column on documents.

Revision ID: 011
Revises: 010
Create Date: 2026-03-01 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "011"
down_revision: str | None = "010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- redactions table (append-only, immutable) ---
    op.create_table(
        "redactions",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("document_id", sa.UUID(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("matter_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("redaction_type", sa.VARCHAR(20), nullable=False),
        sa.Column("pii_category", sa.VARCHAR(20), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("span_start", sa.Integer(), nullable=True),
        sa.Column("span_end", sa.Integer(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("original_text_hash", sa.VARCHAR(64), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_redactions_document", "redactions", ["document_id", "matter_id"])
    op.create_index("ix_redactions_created", "redactions", ["created_at"])

    # --- redacted_pdf_path column on documents ---
    op.add_column("documents", sa.Column("redacted_pdf_path", sa.VARCHAR(500), nullable=True))


def downgrade() -> None:
    op.drop_column("documents", "redacted_pdf_path")
    op.drop_index("ix_redactions_created", table_name="redactions")
    op.drop_index("ix_redactions_document", table_name="redactions")
    op.drop_table("redactions")
