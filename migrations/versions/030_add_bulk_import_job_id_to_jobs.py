"""Add bulk_import_job_id FK to jobs table.

Links individual ingestion jobs back to their parent bulk import job,
enabling drill-down from the bulk import list to per-document job status.

Revision ID: 030
Revises: 029
Create Date: 2026-03-20 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "030"
down_revision: str | None = "029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column(
            "bulk_import_job_id",
            sa.UUID(),
            sa.ForeignKey("bulk_import_jobs.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("idx_jobs_bulk_import_job_id", "jobs", ["bulk_import_job_id"])


def downgrade() -> None:
    op.drop_index("idx_jobs_bulk_import_job_id", table_name="jobs")
    op.drop_column("jobs", "bulk_import_job_id")
