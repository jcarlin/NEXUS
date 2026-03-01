"""Dataset and collection management tables.

Adds folder-tree structure (datasets), many-to-many document assignment
(dataset_documents), cross-cutting document tags (document_tags), and
per-dataset access control (dataset_access).  Also adds nullable dataset_id
foreign key to the jobs table so ingestion can target a specific dataset.

Revision ID: 013
Revises: 012
Create Date: 2026-03-01 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "013"
down_revision: str | None = "012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- datasets: folder tree within a matter ---
    op.create_table(
        "datasets",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("matter_id", sa.UUID(), sa.ForeignKey("matters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("parent_id", sa.UUID(), sa.ForeignKey("datasets.id", ondelete="CASCADE"), nullable=True),
        sa.Column("created_by", sa.UUID(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("matter_id", "parent_id", "name", name="uq_datasets_matter_parent_name"),
    )
    op.create_index("ix_datasets_matter_id", "datasets", ["matter_id"])
    op.create_index("ix_datasets_parent_id", "datasets", ["parent_id"])

    # --- dataset_documents: many-to-many junction ---
    op.create_table(
        "dataset_documents",
        sa.Column("dataset_id", sa.UUID(), sa.ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", sa.UUID(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("assigned_by", sa.UUID(), sa.ForeignKey("users.id"), nullable=True),
        sa.PrimaryKeyConstraint("dataset_id", "document_id"),
    )
    op.create_index("ix_dataset_documents_document_id", "dataset_documents", ["document_id"])

    # --- document_tags: cross-cutting labels ---
    op.create_table(
        "document_tags",
        sa.Column("document_id", sa.UUID(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tag_name", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.UUID(), sa.ForeignKey("users.id"), nullable=True),
        sa.PrimaryKeyConstraint("document_id", "tag_name"),
    )
    op.create_index("ix_document_tags_tag_name", "document_tags", ["tag_name"])

    # --- dataset_access: per-dataset permission overrides ---
    op.create_table(
        "dataset_access",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("dataset_id", sa.UUID(), sa.ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("access_role", sa.String(20), nullable=False, server_default="viewer"),
        sa.Column("granted_by", sa.UUID(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("granted_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("dataset_id", "user_id", name="uq_dataset_access_dataset_user"),
    )
    op.create_index("ix_dataset_access_dataset_id", "dataset_access", ["dataset_id"])

    # --- Add dataset_id to jobs table ---
    op.add_column(
        "jobs",
        sa.Column("dataset_id", sa.UUID(), sa.ForeignKey("datasets.id", ondelete="SET NULL"), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("jobs", "dataset_id")
    op.drop_table("dataset_access")
    op.drop_table("document_tags")
    op.drop_table("dataset_documents")
    op.drop_table("datasets")
