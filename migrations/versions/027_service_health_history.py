"""Add service_health_history table for uptime tracking.

Stores periodic health check results for all backing services.
Feature-flagged: ENABLE_SERVICE_OPERATIONS.

Revision ID: 027
Revises: 026
Create Date: 2026-03-14 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "027"
down_revision: str | None = "026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "service_health_history",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("service_name", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_shh_service_checked",
        "service_health_history",
        ["service_name", sa.text("checked_at DESC")],
    )
    op.create_index(
        "ix_shh_checked_at",
        "service_health_history",
        [sa.text("checked_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_shh_checked_at")
    op.drop_index("ix_shh_service_checked")
    op.drop_table("service_health_history")
