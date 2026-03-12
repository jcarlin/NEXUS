"""Add feature_flag_overrides table for runtime flag management.

Stores admin-toggled feature flag values that override env defaults.
One row per overridden flag. Missing = use env default.

Revision ID: 021
Revises: 020
Create Date: 2026-03-12 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "021"
down_revision: str | None = "020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE feature_flag_overrides (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            flag_name   VARCHAR(80) NOT NULL UNIQUE,
            enabled     BOOLEAN NOT NULL,
            updated_by  UUID REFERENCES users(id),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS feature_flag_overrides")
