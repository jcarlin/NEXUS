"""Bulk import: import_source column, content_hash index, bulk_import_jobs table.

Revision ID: 007
Revises: 006
Create Date: 2026-02-28 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "007"
down_revision: str | None = "006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- Add import_source column to documents ---
    op.add_column(
        "documents",
        sa.Column("import_source", sa.String(128), nullable=True),
    )

    # --- B-tree index on documents(content_hash) for fast --resume lookups ---
    op.create_index(
        "idx_documents_content_hash",
        "documents",
        ["content_hash"],
    )

    # --- bulk_import_jobs table ---
    op.create_table(
        "bulk_import_jobs",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("matter_id", sa.Uuid(), nullable=False),
        sa.Column("adapter_type", sa.String(64), nullable=True),
        sa.Column("source_path", sa.String(1024), nullable=True),
        sa.Column(
            "status",
            sa.String(50),
            nullable=False,
            server_default="'pending'",
        ),
        sa.Column("total_documents", sa.Integer(), nullable=True),
        sa.Column(
            "processed_documents",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "failed_documents",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "skipped_documents",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("metadata_", sa.JSON(), nullable=True),
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
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_bulk_import_jobs_matter_id",
        "bulk_import_jobs",
        ["matter_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_bulk_import_jobs_matter_id", table_name="bulk_import_jobs")
    op.drop_table("bulk_import_jobs")
    op.drop_index("idx_documents_content_hash", table_name="documents")
    op.drop_column("documents", "import_source")
