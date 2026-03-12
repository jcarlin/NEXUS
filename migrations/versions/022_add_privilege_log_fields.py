"""Add privilege_basis, privilege_log_excluded columns and partial index.

Supports court-formatted privilege log generation with per-document
basis text and the ability to exclude specific documents from the log.

Revision ID: 022
Revises: 021
Create Date: 2026-03-12 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "022"
down_revision: str | None = "021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE documents ADD COLUMN privilege_basis TEXT")
    op.execute("ALTER TABLE documents ADD COLUMN privilege_log_excluded BOOLEAN DEFAULT FALSE")
    op.execute(
        "CREATE INDEX idx_docs_privilege ON documents(matter_id, privilege_status) WHERE privilege_status IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_docs_privilege")
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS privilege_log_excluded")
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS privilege_basis")
