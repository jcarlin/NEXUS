"""EDRM interop, email threading, near-duplicate detection, and version tracking.

Revision ID: 005
Revises: 003
Create Date: 2026-02-28 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Email threading columns on documents ---
    op.add_column("documents", sa.Column("message_id", sa.String(512), nullable=True))
    op.add_column("documents", sa.Column("in_reply_to", sa.String(512), nullable=True))
    op.add_column("documents", sa.Column("references_", sa.Text(), nullable=True))
    op.add_column("documents", sa.Column("thread_id", sa.String(128), nullable=True))
    op.add_column("documents", sa.Column("thread_position", sa.Integer(), nullable=True))
    op.add_column("documents", sa.Column("is_inclusive", sa.Boolean(), nullable=True))

    # --- Near-duplicate detection columns on documents ---
    op.add_column("documents", sa.Column("duplicate_cluster_id", sa.String(128), nullable=True))
    op.add_column("documents", sa.Column("duplicate_score", sa.Float(), nullable=True))

    # --- Version tracking columns on documents ---
    op.add_column("documents", sa.Column("version_group_id", sa.String(128), nullable=True))
    op.add_column("documents", sa.Column("version_number", sa.Integer(), nullable=True))
    op.add_column("documents", sa.Column("is_final_version", sa.Boolean(), nullable=True))

    # --- Indexes ---
    op.create_index("ix_documents_thread_id", "documents", ["thread_id"])
    op.create_index("ix_documents_message_id", "documents", ["message_id"])
    op.create_index("ix_documents_duplicate_cluster_id", "documents", ["duplicate_cluster_id"])
    op.create_index("ix_documents_version_group_id", "documents", ["version_group_id"])

    # --- edrm_import_log table ---
    op.create_table(
        "edrm_import_log",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("matter_id", sa.Uuid(), nullable=False),
        sa.Column("filename", sa.String(500), nullable=False),
        sa.Column("format", sa.String(50), nullable=False),
        sa.Column("record_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(50), nullable=False, server_default="'pending'"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_edrm_import_log_matter_id", "edrm_import_log", ["matter_id"])


def downgrade() -> None:
    op.drop_index("ix_edrm_import_log_matter_id", table_name="edrm_import_log")
    op.drop_table("edrm_import_log")

    op.drop_index("ix_documents_version_group_id", table_name="documents")
    op.drop_index("ix_documents_duplicate_cluster_id", table_name="documents")
    op.drop_index("ix_documents_message_id", table_name="documents")
    op.drop_index("ix_documents_thread_id", table_name="documents")

    op.drop_column("documents", "is_final_version")
    op.drop_column("documents", "version_number")
    op.drop_column("documents", "version_group_id")
    op.drop_column("documents", "duplicate_score")
    op.drop_column("documents", "duplicate_cluster_id")
    op.drop_column("documents", "is_inclusive")
    op.drop_column("documents", "thread_position")
    op.drop_column("documents", "thread_id")
    op.drop_column("documents", "references_")
    op.drop_column("documents", "in_reply_to")
    op.drop_column("documents", "message_id")
