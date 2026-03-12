"""Add unique index for datasets with NULL parent_id.

The existing constraint uq_datasets_matter_parent_name on (matter_id, parent_id, name)
does not prevent duplicates when parent_id IS NULL because NULL != NULL in SQL.
This migration cleans up existing duplicates and adds a partial unique index
covering the NULL parent_id case.

Revision ID: 020
Revises: 019
Create Date: 2026-03-12 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "020"
down_revision: str | None = "019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Step 1: Delete duplicate root-level datasets (keep oldest by id).
    op.execute(
        """
        DELETE FROM datasets a
        USING datasets b
        WHERE a.matter_id = b.matter_id
          AND a.name = b.name
          AND a.parent_id IS NULL
          AND b.parent_id IS NULL
          AND a.id > b.id
        """
    )

    # Step 2: Add partial unique index for NULL parent_id rows.
    # The existing constraint already covers non-NULL parent_id.
    op.execute(
        """
        CREATE UNIQUE INDEX uq_datasets_matter_name_root
        ON datasets (matter_id, name)
        WHERE parent_id IS NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_datasets_matter_name_root")
