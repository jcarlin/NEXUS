"""Add external_tasks table for ad-hoc script tracking.

Scripts can register as tracked tasks via the /api/v1/scripts/tasks API
and appear in the pipeline UI's Scripts tab.

Revision ID: 035
Revises: 034
Create Date: 2026-03-27
"""

import sqlalchemy as sa
from alembic import op

revision = "035"
down_revision = "034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "external_tasks",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("script_name", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="running", nullable=False),
        sa.Column("total", sa.Integer(), server_default="0", nullable=False),
        sa.Column("processed", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failed", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("metadata_", sa.JSON(), server_default=sa.text("'{}'::jsonb"), nullable=True),
        sa.Column("matter_id", sa.Uuid(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_external_tasks_status", "external_tasks", ["status"])
    op.create_index("idx_external_tasks_updated", "external_tasks", ["updated_at"])


def downgrade() -> None:
    op.drop_index("idx_external_tasks_updated", table_name="external_tasks")
    op.drop_index("idx_external_tasks_status", table_name="external_tasks")
    op.drop_table("external_tasks")
