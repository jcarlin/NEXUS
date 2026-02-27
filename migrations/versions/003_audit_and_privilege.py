"""Audit log table and privilege columns on documents.

Revision ID: 003
Revises: 002
Create Date: 2026-02-26 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- audit_log table ---
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("user_email", sa.String(255), nullable=True),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("resource", sa.String(500), nullable=False),
        sa.Column("resource_type", sa.String(100), nullable=True),
        sa.Column("matter_id", sa.Uuid(), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=False),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Float(), nullable=True),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_audit_log_created_at", "audit_log", [sa.text("created_at DESC")])
    op.create_index("ix_audit_log_user_id", "audit_log", ["user_id"])
    op.create_index("ix_audit_log_matter_id", "audit_log", ["matter_id"])
    op.create_index("ix_audit_log_resource_type", "audit_log", ["resource_type"])

    # --- Privilege columns on documents ---
    op.add_column("documents", sa.Column("privilege_status", sa.String(50), nullable=True))
    op.add_column(
        "documents",
        sa.Column(
            "privilege_reviewed_by",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "documents",
        sa.Column("privilege_reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_documents_privilege_status", "documents", ["privilege_status"])


def downgrade() -> None:
    op.drop_index("ix_documents_privilege_status", table_name="documents")
    op.drop_column("documents", "privilege_reviewed_at")
    op.drop_column("documents", "privilege_reviewed_by")
    op.drop_column("documents", "privilege_status")

    op.drop_index("ix_audit_log_resource_type", table_name="audit_log")
    op.drop_index("ix_audit_log_matter_id", table_name="audit_log")
    op.drop_index("ix_audit_log_user_id", table_name="audit_log")
    op.drop_index("ix_audit_log_created_at", table_name="audit_log")
    op.drop_table("audit_log")
