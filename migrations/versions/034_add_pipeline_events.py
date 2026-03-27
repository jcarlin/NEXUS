"""Add pipeline_events table for task lifecycle tracking.

Stores events like TASK_RECEIVED, STAGE_STARTED, STAGE_COMPLETED, TASK_FAILED,
TASK_RETRIED, WORKER_ONLINE, WORKER_OFFLINE.

Revision ID: 034
Revises: 033
Create Date: 2026-03-27
"""

import sqlalchemy as sa
from alembic import op

revision = "034"
down_revision = "033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pipeline_events",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("worker", sa.Text(), nullable=True),
        sa.Column("detail", sa.JSON(), server_default=sa.text("'{}'::jsonb"), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_pipeline_events_job_id", "pipeline_events", ["job_id"])
    op.create_index("idx_pipeline_events_timestamp", "pipeline_events", ["timestamp"], postgresql_using="btree")
    op.create_index("idx_pipeline_events_type", "pipeline_events", ["event_type"])


def downgrade() -> None:
    op.drop_index("idx_pipeline_events_type", table_name="pipeline_events")
    op.drop_index("idx_pipeline_events_timestamp", table_name="pipeline_events")
    op.drop_index("idx_pipeline_events_job_id", table_name="pipeline_events")
    op.drop_table("pipeline_events")
