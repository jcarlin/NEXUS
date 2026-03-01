"""Sentiment analysis and hot doc detection columns on documents table.

Revision ID: 009
Revises: 008
Create Date: 2026-02-28 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "009"
down_revision: str | None = "008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- Sentiment scores ---
    op.add_column("documents", sa.Column("sentiment_positive", sa.Float(), nullable=True))
    op.add_column("documents", sa.Column("sentiment_negative", sa.Float(), nullable=True))
    op.add_column("documents", sa.Column("sentiment_pressure", sa.Float(), nullable=True))
    op.add_column("documents", sa.Column("sentiment_opportunity", sa.Float(), nullable=True))
    op.add_column("documents", sa.Column("sentiment_rationalization", sa.Float(), nullable=True))
    op.add_column("documents", sa.Column("sentiment_intent", sa.Float(), nullable=True))
    op.add_column("documents", sa.Column("sentiment_concealment", sa.Float(), nullable=True))

    # --- Hot doc detection ---
    op.add_column("documents", sa.Column("hot_doc_score", sa.Float(), nullable=True))
    op.add_column("documents", sa.Column("context_gap_score", sa.Float(), nullable=True))
    op.add_column(
        "documents",
        sa.Column("context_gaps", JSONB(), nullable=True),
    )
    op.add_column("documents", sa.Column("anomaly_score", sa.Float(), nullable=True))

    # --- Indexes for query tool performance ---
    op.create_index("ix_documents_hot_doc_score", "documents", ["hot_doc_score"])
    op.create_index("ix_documents_context_gap_score", "documents", ["context_gap_score"])
    op.create_index("ix_documents_anomaly_score", "documents", ["anomaly_score"])


def downgrade() -> None:
    op.drop_index("ix_documents_anomaly_score", table_name="documents")
    op.drop_index("ix_documents_context_gap_score", table_name="documents")
    op.drop_index("ix_documents_hot_doc_score", table_name="documents")

    op.drop_column("documents", "anomaly_score")
    op.drop_column("documents", "context_gaps")
    op.drop_column("documents", "context_gap_score")
    op.drop_column("documents", "hot_doc_score")
    op.drop_column("documents", "sentiment_concealment")
    op.drop_column("documents", "sentiment_intent")
    op.drop_column("documents", "sentiment_rationalization")
    op.drop_column("documents", "sentiment_opportunity")
    op.drop_column("documents", "sentiment_pressure")
    op.drop_column("documents", "sentiment_negative")
    op.drop_column("documents", "sentiment_positive")
