"""Add missing indexes on foreign key columns.

Tables: memos.created_by, document_tags.document_id, document_tags.created_by

Revision ID: 036
Revises: 035
Create Date: 2026-03-28
"""

from alembic import op

revision = "036"
down_revision = "035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_memos_created_by", "memos", ["created_by"])
    op.create_index("ix_document_tags_document_id", "document_tags", ["document_id"])
    op.create_index("ix_document_tags_created_by", "document_tags", ["created_by"])


def downgrade() -> None:
    op.drop_index("ix_document_tags_created_by", table_name="document_tags")
    op.drop_index("ix_document_tags_document_id", table_name="document_tags")
    op.drop_index("ix_memos_created_by", table_name="memos")
