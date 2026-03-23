"""Add composite indexes on jobs(matter_id, status) and jobs(bulk_import_job_id, status).

These indexes eliminate sequential scans on the 20K+ row jobs table during
pipeline dashboard polling (every 5-10s filtering by status).

Revision ID: 032
Revises: 031
Create Date: 2026-03-23
"""

from alembic import op

revision = "032"
down_revision = "031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "idx_jobs_matter_status",
        "jobs",
        ["matter_id", "status"],
        if_not_exists=True,
    )
    op.create_index(
        "idx_jobs_bulk_import_status",
        "jobs",
        ["bulk_import_job_id", "status"],
        postgresql_where="bulk_import_job_id IS NOT NULL",
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index("idx_jobs_bulk_import_status", table_name="jobs")
    op.drop_index("idx_jobs_matter_status", table_name="jobs")
