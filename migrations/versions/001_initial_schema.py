"""Initial schema: jobs, documents, chat_messages tables.

Revision ID: 001
Revises: None
Create Date: 2025-01-01 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # jobs — tracks ingestion pipeline runs
    # ------------------------------------------------------------------
    op.create_table(
        "jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("filename", sa.String, nullable=False),
        sa.Column("status", sa.String, nullable=False, server_default="pending"),
        sa.Column("stage", sa.String, server_default="uploading"),
        sa.Column("progress", JSONB, server_default="{}"),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("parent_job_id", UUID(as_uuid=True), sa.ForeignKey("jobs.id"), nullable=True),
        sa.Column("metadata_", JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # ------------------------------------------------------------------
    # documents — ingested document metadata
    # ------------------------------------------------------------------
    op.create_table(
        "documents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("job_id", UUID(as_uuid=True), sa.ForeignKey("jobs.id"), nullable=True),
        sa.Column("filename", sa.String, nullable=False),
        sa.Column("document_type", sa.String, nullable=True),
        sa.Column("page_count", sa.Integer, server_default="0"),
        sa.Column("chunk_count", sa.Integer, server_default="0"),
        sa.Column("entity_count", sa.Integer, server_default="0"),
        sa.Column("minio_path", sa.String, nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger, nullable=True),
        sa.Column("content_hash", sa.String, nullable=True),
        sa.Column("metadata_", JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # ------------------------------------------------------------------
    # chat_messages — conversation history (query domain)
    # ------------------------------------------------------------------
    op.create_table(
        "chat_messages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("thread_id", UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("source_documents", JSONB, server_default="[]"),
        sa.Column("entities_mentioned", JSONB, server_default="[]"),
        sa.Column("follow_up_questions", JSONB, server_default="[]"),
        sa.Column("metadata_", JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # Index for efficient chat-history lookups ordered by time.
    op.create_index(
        "idx_chat_messages_thread",
        "chat_messages",
        ["thread_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_chat_messages_thread", table_name="chat_messages")
    op.drop_table("chat_messages")
    op.drop_table("documents")
    op.drop_table("jobs")
