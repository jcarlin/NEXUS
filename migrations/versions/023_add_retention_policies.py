"""Add retention_policies table and is_archived column on case_matters.

Supports data retention lifecycle management: set per-matter retention
periods, schedule purges, archive-before-purge, cascading data deletion.

Revision ID: 023
Revises: 022
Create Date: 2026-03-12 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "023"
down_revision: str | None = "022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE retention_policies (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            matter_id UUID NOT NULL REFERENCES case_matters(id) UNIQUE,
            retention_days INTEGER NOT NULL,
            policy_set_by UUID NOT NULL REFERENCES users(id),
            policy_set_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            purge_scheduled_at TIMESTAMPTZ,
            purge_completed_at TIMESTAMPTZ,
            purge_error TEXT,
            archive_path TEXT,
            status TEXT NOT NULL DEFAULT 'active'
        )
    """)
    op.execute("ALTER TABLE case_matters ADD COLUMN is_archived BOOLEAN DEFAULT FALSE")


def downgrade() -> None:
    op.execute("ALTER TABLE case_matters DROP COLUMN IF EXISTS is_archived")
    op.execute("DROP TABLE IF EXISTS retention_policies")
