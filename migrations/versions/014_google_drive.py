"""Google Drive integration tables.

Adds ``google_drive_connections`` (encrypted OAuth tokens) and
``google_drive_sync_state`` (incremental sync tracking).

Revision ID: 014
Revises: 013
Create Date: 2026-03-08 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "014"
down_revision: str | None = "013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- google_drive_connections: OAuth token storage (encrypted at rest) ---
    op.create_table(
        "google_drive_connections",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("user_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("matter_id", sa.UUID(), sa.ForeignKey("case_matters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("connection_type", sa.String(20), nullable=False, server_default="oauth"),
        sa.Column("encrypted_tokens", sa.Text(), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("scopes", sa.Text(), server_default="", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("user_id", "matter_id", "email", name="uq_gdrive_conn_user_matter_email"),
    )
    op.create_index("ix_gdrive_connections_matter_id", "google_drive_connections", ["matter_id"])
    op.create_index("ix_gdrive_connections_user_id", "google_drive_connections", ["user_id"])

    # --- google_drive_sync_state: incremental sync tracking ---
    op.create_table(
        "google_drive_sync_state",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column(
            "connection_id",
            sa.UUID(),
            sa.ForeignKey("google_drive_connections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("matter_id", sa.UUID(), sa.ForeignKey("case_matters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("drive_file_id", sa.String(255), nullable=False),
        sa.Column("drive_file_name", sa.String(1024), nullable=False),
        sa.Column("drive_modified_time", sa.String(64), nullable=True),
        sa.Column("content_hash", sa.String(128), nullable=True),
        sa.Column("document_id", sa.UUID(), sa.ForeignKey("documents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sync_status", sa.String(20), server_default="pending", nullable=False),
        sa.UniqueConstraint("connection_id", "drive_file_id", name="uq_gdrive_sync_conn_file"),
    )
    op.create_index("ix_gdrive_sync_connection_id", "google_drive_sync_state", ["connection_id"])
    op.create_index("ix_gdrive_sync_matter_id", "google_drive_sync_state", ["matter_id"])


def downgrade() -> None:
    op.drop_table("google_drive_sync_state")
    op.drop_table("google_drive_connections")
