"""SOC 2 audit readiness: AI audit log, agent audit log, session tracking, immutability rules.

Revision ID: 004
Revises: 003
Create Date: 2026-02-28 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- ai_audit_log table ---
    op.create_table(
        "ai_audit_log",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column("session_id", sa.Uuid(), nullable=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("matter_id", sa.Uuid(), nullable=True),
        sa.Column("call_type", sa.String(50), nullable=False, server_default="completion"),
        sa.Column("node_name", sa.String(100), nullable=True),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("prompt_hash", sa.String(64), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="success"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("metadata_", sa.JSON(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_ai_audit_log_created_at", "ai_audit_log", [sa.text("created_at DESC")])
    op.create_index("ix_ai_audit_log_session_id", "ai_audit_log", ["session_id"])
    op.create_index("ix_ai_audit_log_user_id", "ai_audit_log", ["user_id"])
    op.create_index("ix_ai_audit_log_request_id", "ai_audit_log", ["request_id"])
    op.create_index("ix_ai_audit_log_matter_id", "ai_audit_log", ["matter_id"])

    # --- agent_audit_log table (schema only — populated by future M10+ agents) ---
    op.create_table(
        "agent_audit_log",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=True),
        sa.Column("agent_id", sa.String(100), nullable=False),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("matter_id", sa.Uuid(), nullable=True),
        sa.Column("action_type", sa.String(100), nullable=False),
        sa.Column("action_name", sa.String(200), nullable=True),
        sa.Column("input_summary", sa.Text(), nullable=True),
        sa.Column("output_summary", sa.Text(), nullable=True),
        sa.Column("iteration_number", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Float(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="success"),
        sa.Column("metadata_", sa.JSON(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_agent_audit_log_created_at", "agent_audit_log", [sa.text("created_at DESC")])
    op.create_index("ix_agent_audit_log_session_id", "agent_audit_log", ["session_id"])
    op.create_index("ix_agent_audit_log_agent_id", "agent_audit_log", ["agent_id"])

    # --- Add session_id to existing audit_log table ---
    op.add_column("audit_log", sa.Column("session_id", sa.Uuid(), nullable=True))
    op.create_index("ix_audit_log_session_id", "audit_log", ["session_id"])

    # --- Immutability rules (PostgreSQL RULEs to prevent UPDATE/DELETE) ---
    op.execute("""
        CREATE RULE audit_log_no_update AS ON UPDATE TO audit_log DO INSTEAD NOTHING;
    """)
    op.execute("""
        CREATE RULE audit_log_no_delete AS ON DELETE TO audit_log DO INSTEAD NOTHING;
    """)
    op.execute("""
        CREATE RULE ai_audit_log_no_update AS ON UPDATE TO ai_audit_log DO INSTEAD NOTHING;
    """)
    op.execute("""
        CREATE RULE ai_audit_log_no_delete AS ON DELETE TO ai_audit_log DO INSTEAD NOTHING;
    """)
    op.execute("""
        CREATE RULE agent_audit_log_no_update AS ON UPDATE TO agent_audit_log DO INSTEAD NOTHING;
    """)
    op.execute("""
        CREATE RULE agent_audit_log_no_delete AS ON DELETE TO agent_audit_log DO INSTEAD NOTHING;
    """)


def downgrade() -> None:
    # --- Remove immutability rules ---
    op.execute("DROP RULE IF EXISTS agent_audit_log_no_delete ON agent_audit_log;")
    op.execute("DROP RULE IF EXISTS agent_audit_log_no_update ON agent_audit_log;")
    op.execute("DROP RULE IF EXISTS ai_audit_log_no_delete ON ai_audit_log;")
    op.execute("DROP RULE IF EXISTS ai_audit_log_no_update ON ai_audit_log;")
    op.execute("DROP RULE IF EXISTS audit_log_no_delete ON audit_log;")
    op.execute("DROP RULE IF EXISTS audit_log_no_update ON audit_log;")

    # --- Remove session_id from audit_log ---
    op.drop_index("ix_audit_log_session_id", table_name="audit_log")
    op.drop_column("audit_log", "session_id")

    # --- Drop agent_audit_log ---
    op.drop_index("ix_agent_audit_log_agent_id", table_name="agent_audit_log")
    op.drop_index("ix_agent_audit_log_session_id", table_name="agent_audit_log")
    op.drop_index("ix_agent_audit_log_created_at", table_name="agent_audit_log")
    op.drop_table("agent_audit_log")

    # --- Drop ai_audit_log ---
    op.drop_index("ix_ai_audit_log_matter_id", table_name="ai_audit_log")
    op.drop_index("ix_ai_audit_log_request_id", table_name="ai_audit_log")
    op.drop_index("ix_ai_audit_log_user_id", table_name="ai_audit_log")
    op.drop_index("ix_ai_audit_log_session_id", table_name="ai_audit_log")
    op.drop_index("ix_ai_audit_log_created_at", table_name="ai_audit_log")
    op.drop_table("ai_audit_log")
