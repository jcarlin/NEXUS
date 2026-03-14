"""Add community_summaries table for GraphRAG community detection.

Stores Louvain community detection results with LLM-generated summaries.
Feature-flagged: ENABLE_GRAPHRAG_COMMUNITIES.

Revision ID: 026
Revises: 025
Create Date: 2026-03-13 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "026"
down_revision: str | None = "025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "community_summaries",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column(
            "matter_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("level", sa.Integer(), server_default="0"),
        sa.Column("parent_id", sa.Text(), nullable=True),
        sa.Column("entity_names", JSONB(), server_default="[]"),
        sa.Column("relationship_types", JSONB(), server_default="[]"),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("entity_count", sa.Integer(), server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_community_summaries_matter_id",
        "community_summaries",
        ["matter_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_community_summaries_matter_id")
    op.drop_table("community_summaries")
