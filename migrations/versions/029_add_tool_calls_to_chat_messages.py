"""Add tool_calls JSONB column to chat_messages.

Stores the list of agent tool invocations for each assistant message,
enabling the frontend to render a persistent activity log.

Revision ID: 029
Revises: 028
Create Date: 2026-03-14 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "029"
down_revision: str | None = "028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "chat_messages",
        sa.Column("tool_calls", sa.JSON(), server_default="[]", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("chat_messages", "tool_calls")
