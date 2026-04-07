"""Add document_date column for real communication dates.

Adds a canonical ``document_date`` TIMESTAMPTZ column to the ``documents``
table to store the actual communication date (email sent date, letter
date, etc.) rather than the ingestion timestamp (``created_at``).

Two partial indexes support matter-scoped chronological queries which
are by far the most common access pattern (entity timeline,
temporal_search). Partial indexes keep size small since most non-email
documents will have NULL values under the strict "no improvised dates"
rule.

Revision ID: 038
Revises: 037
Create Date: 2026-04-06
"""

from alembic import op

revision = "038"
down_revision = "037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE documents ADD COLUMN document_date TIMESTAMPTZ")
    op.execute("CREATE INDEX idx_documents_document_date ON documents (document_date) WHERE document_date IS NOT NULL")
    op.execute(
        "CREATE INDEX idx_documents_matter_date ON documents (matter_id, document_date) WHERE document_date IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_documents_matter_date")
    op.execute("DROP INDEX IF EXISTS idx_documents_document_date")
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS document_date")
