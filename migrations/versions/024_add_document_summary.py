"""Add summary column to documents table for document summarization.

Stores a 2-3 sentence LLM-generated summary per document at ingestion time.
Feature-flagged: ENABLE_DOCUMENT_SUMMARIZATION.

Revision ID: 024
Revises: 023
Create Date: 2026-03-12 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "024"
down_revision: str | None = "023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE documents ADD COLUMN summary TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS summary")
