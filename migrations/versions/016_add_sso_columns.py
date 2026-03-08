"""Add SSO columns to users table.

Revision ID: 016
Revises: 015
Create Date: 2026-03-08 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "016"
down_revision: str | None = "015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add SSO columns (both nullable — only populated for SSO users)
    op.add_column("users", sa.Column("sso_provider", sa.String(50), nullable=True))
    op.add_column("users", sa.Column("sso_subject_id", sa.String(255), nullable=True))

    # Unique index on (sso_provider, sso_subject_id) where both are NOT NULL
    op.create_index(
        "ix_users_sso_provider_subject",
        "users",
        ["sso_provider", "sso_subject_id"],
        unique=True,
        postgresql_where=sa.text("sso_provider IS NOT NULL AND sso_subject_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_users_sso_provider_subject", table_name="users")
    op.drop_column("users", "sso_subject_id")
    op.drop_column("users", "sso_provider")
