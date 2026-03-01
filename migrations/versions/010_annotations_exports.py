"""Annotations, production sets, and export jobs tables.

Revision ID: 010
Revises: 009
Create Date: 2026-02-28 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "010"
down_revision: str | None = "009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- annotations ---
    op.create_table(
        "annotations",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("document_id", sa.UUID(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("matter_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("annotation_type", sa.VARCHAR(50), server_default="note", nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("anchor", JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("color", sa.VARCHAR(20), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_annotations_matter_id", "annotations", ["matter_id"])
    op.create_index("ix_annotations_document_id", "annotations", ["document_id"])
    op.create_index("ix_annotations_user_id", "annotations", ["user_id"])

    # --- production_sets ---
    op.create_table(
        "production_sets",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("matter_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.VARCHAR(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("bates_prefix", sa.VARCHAR(50), server_default="NEXUS", nullable=False),
        sa.Column("bates_start", sa.Integer(), server_default="1", nullable=False),
        sa.Column("bates_padding", sa.Integer(), server_default="6", nullable=False),
        sa.Column("next_bates", sa.Integer(), server_default="1", nullable=False),
        sa.Column("status", sa.VARCHAR(50), server_default="draft", nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("matter_id", "name", name="uq_production_sets_matter_name"),
    )
    op.create_index("ix_production_sets_matter_id", "production_sets", ["matter_id"])

    # --- production_set_documents ---
    op.create_table(
        "production_set_documents",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column(
            "production_set_id", sa.UUID(), sa.ForeignKey("production_sets.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("document_id", sa.UUID(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("bates_begin", sa.VARCHAR(100), nullable=True),
        sa.Column("bates_end", sa.VARCHAR(100), nullable=True),
        sa.Column("added_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("production_set_id", "document_id", name="uq_psd_set_document"),
    )

    # --- export_jobs ---
    op.create_table(
        "export_jobs",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("matter_id", sa.UUID(), nullable=False),
        sa.Column("export_type", sa.VARCHAR(50), nullable=False),
        sa.Column("export_format", sa.VARCHAR(20), server_default="zip", nullable=False),
        sa.Column("status", sa.VARCHAR(50), server_default="pending", nullable=False),
        sa.Column("parameters", JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("output_path", sa.VARCHAR(500), nullable=True),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index("ix_export_jobs_matter_id", "export_jobs", ["matter_id"])

    # --- bates columns on documents ---
    op.add_column("documents", sa.Column("bates_begin", sa.VARCHAR(100), nullable=True))
    op.add_column("documents", sa.Column("bates_end", sa.VARCHAR(100), nullable=True))
    op.create_index("ix_documents_bates_begin", "documents", ["bates_begin"])


def downgrade() -> None:
    op.drop_index("ix_documents_bates_begin", table_name="documents")
    op.drop_column("documents", "bates_end")
    op.drop_column("documents", "bates_begin")

    op.drop_index("ix_export_jobs_matter_id", table_name="export_jobs")
    op.drop_table("export_jobs")

    op.drop_table("production_set_documents")

    op.drop_index("ix_production_sets_matter_id", table_name="production_sets")
    op.drop_table("production_sets")

    op.drop_index("ix_annotations_user_id", table_name="annotations")
    op.drop_index("ix_annotations_document_id", table_name="annotations")
    op.drop_index("ix_annotations_matter_id", table_name="annotations")
    op.drop_table("annotations")
