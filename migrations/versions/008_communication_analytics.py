"""Communication analytics: communication_pairs and org_chart_entries tables.

Revision ID: 008
Revises: 007
Create Date: 2026-02-28 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "008"
down_revision: str | None = "007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- communication_pairs table ---
    op.create_table(
        "communication_pairs",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("matter_id", sa.Uuid(), nullable=False),
        sa.Column("sender_name", sa.String(500), nullable=False),
        sa.Column("sender_email", sa.String(500), nullable=True),
        sa.Column("recipient_name", sa.String(500), nullable=False),
        sa.Column("recipient_email", sa.String(500), nullable=True),
        sa.Column(
            "relationship_type",
            sa.String(10),
            nullable=False,
            server_default="'to'",
        ),
        sa.Column(
            "message_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("earliest", sa.DateTime(timezone=True), nullable=True),
        sa.Column("latest", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "matter_id",
            "sender_email",
            "recipient_email",
            "relationship_type",
            name="uq_comm_pairs_sender_recipient_type",
        ),
    )
    op.create_index(
        "ix_comm_pairs_matter",
        "communication_pairs",
        ["matter_id"],
    )

    # --- org_chart_entries table ---
    op.create_table(
        "org_chart_entries",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("matter_id", sa.Uuid(), nullable=False),
        sa.Column("person_name", sa.String(500), nullable=False),
        sa.Column("person_email", sa.String(500), nullable=True),
        sa.Column("reports_to_name", sa.String(500), nullable=True),
        sa.Column("reports_to_email", sa.String(500), nullable=True),
        sa.Column("title", sa.String(500), nullable=True),
        sa.Column("department", sa.String(500), nullable=True),
        sa.Column(
            "source",
            sa.String(50),
            nullable=False,
            server_default="'manual'",
        ),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("confirmed_by", sa.Uuid(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_org_chart_matter",
        "org_chart_entries",
        ["matter_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_org_chart_matter", table_name="org_chart_entries")
    op.drop_table("org_chart_entries")
    op.drop_index("ix_comm_pairs_matter", table_name="communication_pairs")
    op.drop_table("communication_pairs")
