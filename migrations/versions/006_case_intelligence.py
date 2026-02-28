"""Case intelligence layer: case contexts, claims, parties, defined terms, investigation sessions.

Revision ID: 006
Revises: 005
Create Date: 2026-02-28 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "006"
down_revision: str | None = "005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- case_contexts ---
    op.create_table(
        "case_contexts",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("matter_id", sa.Uuid(), nullable=False),
        sa.Column("anchor_document_id", sa.String(256), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="'processing'"),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("confirmed_by", sa.Uuid(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("job_id", sa.String(256), nullable=True),
        sa.Column("timeline", sa.JSON(), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_case_contexts_matter_id", "case_contexts", ["matter_id"], unique=True)

    # --- case_claims ---
    op.create_table(
        "case_claims",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("case_context_id", sa.Uuid(), nullable=False),
        sa.Column("claim_number", sa.Integer(), nullable=False),
        sa.Column("claim_label", sa.String(500), nullable=False),
        sa.Column("claim_text", sa.Text(), nullable=False),
        sa.Column("legal_elements", sa.JSON(), nullable=True),
        sa.Column("source_pages", sa.JSON(), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["case_context_id"], ["case_contexts.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_case_claims_context_id", "case_claims", ["case_context_id"])

    # --- case_parties ---
    op.create_table(
        "case_parties",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("case_context_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("role", sa.String(50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("aliases", sa.JSON(), nullable=True),
        sa.Column("entity_id", sa.String(256), nullable=True),
        sa.Column("source_pages", sa.JSON(), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["case_context_id"], ["case_contexts.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_case_parties_context_id", "case_parties", ["case_context_id"])

    # --- case_defined_terms ---
    op.create_table(
        "case_defined_terms",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("case_context_id", sa.Uuid(), nullable=False),
        sa.Column("term", sa.String(500), nullable=False),
        sa.Column("definition", sa.Text(), nullable=False),
        sa.Column("entity_id", sa.String(256), nullable=True),
        sa.Column("source_pages", sa.JSON(), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["case_context_id"], ["case_contexts.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_case_defined_terms_context_id", "case_defined_terms", ["case_context_id"])

    # --- investigation_sessions ---
    op.create_table(
        "investigation_sessions",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("matter_id", sa.Uuid(), nullable=False),
        sa.Column("case_context_id", sa.Uuid(), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(500), nullable=True),
        sa.Column("findings", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="'active'"),
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
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["case_context_id"], ["case_contexts.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_investigation_sessions_matter_id", "investigation_sessions", ["matter_id"])


def downgrade() -> None:
    op.drop_index("ix_investigation_sessions_matter_id", table_name="investigation_sessions")
    op.drop_table("investigation_sessions")

    op.drop_index("ix_case_defined_terms_context_id", table_name="case_defined_terms")
    op.drop_table("case_defined_terms")

    op.drop_index("ix_case_parties_context_id", table_name="case_parties")
    op.drop_table("case_parties")

    op.drop_index("ix_case_claims_context_id", table_name="case_claims")
    op.drop_table("case_claims")

    op.drop_index("ix_case_contexts_matter_id", table_name="case_contexts")
    op.drop_table("case_contexts")
