"""Add UNIQUE constraint on documents.job_id for idempotent ingestion.

Celery tasks use acks_late + reject_on_worker_lost, so worker death
causes task re-delivery.  Without a UNIQUE constraint on job_id,
each retry creates a duplicate document record.  This migration
cleans up existing duplicates (keeping the most recent per job_id)
and adds the constraint to prevent future duplicates.

Revision ID: 031
Revises: 030
Create Date: 2026-03-21 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "031"
down_revision: str | None = "030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Delete duplicate document records (keep the most recent per job_id)
    op.execute(
        """
        DELETE FROM documents
        WHERE id IN (
            SELECT id FROM (
                SELECT id, ROW_NUMBER() OVER (
                    PARTITION BY job_id ORDER BY created_at DESC
                ) AS rn
                FROM documents
                WHERE job_id IS NOT NULL
            ) ranked
            WHERE rn > 1
        )
        """
    )
    op.create_unique_constraint("uq_documents_job_id", "documents", ["job_id"])


def downgrade() -> None:
    op.drop_constraint("uq_documents_job_id", "documents", type_="unique")
