"""Add shared_chats table for shareable chat links.

Revision ID: 037
Revises: 036
Create Date: 2026-03-31
"""

from alembic import op

revision = "037"
down_revision = "036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE shared_chats (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            thread_id       UUID NOT NULL,
            matter_id       UUID NOT NULL,
            share_token     VARCHAR(22) NOT NULL UNIQUE,
            created_by      UUID NOT NULL,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            expires_at      TIMESTAMPTZ,
            is_revoked      BOOLEAN NOT NULL DEFAULT false,
            view_count      INTEGER NOT NULL DEFAULT 0,
            allow_follow_ups BOOLEAN NOT NULL DEFAULT true
        )
    """)
    op.execute(
        "CREATE INDEX idx_shared_chats_token ON shared_chats (share_token) WHERE NOT is_revoked"
    )
    op.execute(
        "CREATE INDEX idx_shared_chats_thread ON shared_chats (thread_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS shared_chats")
