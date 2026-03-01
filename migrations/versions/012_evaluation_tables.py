"""Evaluation pipeline tables: dataset items and runs.

Revision ID: 012
Revises: 011
Create Date: 2026-03-01 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "012"
down_revision: str | None = "011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "evaluation_dataset_items",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("dataset_type", sa.String(50), nullable=False, index=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("expected_answer", sa.Text(), nullable=False),
        sa.Column("tags", sa.JSON(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("metadata_", sa.JSON(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "evaluation_runs",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("mode", sa.String(20), nullable=False, server_default="full"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("metrics", sa.JSON(), nullable=True),
        sa.Column("config_overrides", sa.JSON(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("total_items", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("processed_items", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("evaluation_runs")
    op.drop_table("evaluation_dataset_items")
