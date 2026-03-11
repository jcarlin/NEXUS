"""Add task_type column to jobs table for generalized background task tracking.

Revision ID: 018
Revises: 017
Create Date: 2026-03-10 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "018"
down_revision: str | None = "017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add task_type column with default 'ingestion' for existing rows
    op.add_column(
        "jobs",
        sa.Column("task_type", sa.String(50), nullable=False, server_default="ingestion"),
    )

    # Add label column for non-ingestion tasks (display name)
    op.add_column(
        "jobs",
        sa.Column("label", sa.String(200), nullable=True),
    )

    # Make filename nullable (non-ingestion tasks use label instead)
    op.alter_column("jobs", "filename", existing_type=sa.Text(), nullable=True)

    # Add composite index for matter + task_type queries
    op.create_index("idx_jobs_matter_task_type", "jobs", ["matter_id", "task_type"])

    # Backfill existing case_setup jobs based on stage values
    op.execute(
        """
        UPDATE jobs SET task_type = 'case_setup'
        WHERE stage IN (
            'extracting_claims', 'extracting_parties',
            'extracting_terms', 'extracting_timeline',
            'populating_graph'
        )
        """
    )


def downgrade() -> None:
    op.drop_index("idx_jobs_matter_task_type", table_name="jobs")

    # Restore filename NOT NULL (set any nulls to empty string first)
    op.execute("UPDATE jobs SET filename = '' WHERE filename IS NULL")
    op.alter_column("jobs", "filename", existing_type=sa.Text(), nullable=False)

    op.drop_column("jobs", "label")
    op.drop_column("jobs", "task_type")
