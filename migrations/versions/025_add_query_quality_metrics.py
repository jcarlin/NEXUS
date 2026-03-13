"""Add query_quality_metrics table for production quality monitoring.

Stores sampled quality scores for production queries: retrieval relevance,
faithfulness, and citation density.
Feature-flagged: ENABLE_PRODUCTION_QUALITY_MONITORING.

Revision ID: 025
Revises: 024
Create Date: 2026-03-12 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "025"
down_revision: str | None = "024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE query_quality_metrics (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            thread_id VARCHAR(255),
            query TEXT NOT NULL,
            query_type VARCHAR(50),
            retrieval_relevance FLOAT,
            faithfulness FLOAT,
            citation_density FLOAT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS query_quality_metrics")
