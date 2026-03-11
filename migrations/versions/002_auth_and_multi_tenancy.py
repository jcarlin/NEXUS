"""Auth tables (users, case_matters, user_case_matters) and matter_id FK on existing tables.

Revision ID: 002
Revises: 001
Create Date: 2026-02-26 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Pre-computed bcrypt hash for "password123" — the seed admin password.
# Generated via: bcrypt.hashpw(b"password123", bcrypt.gensalt()).decode()
_ADMIN_PASSWORD_HASH = "$2b$12$DM4w/5eCr4iJXwTYrOmfnOK4dH9VdaV4phByXOCTXxbu9ea.qxVE6"
_ADMIN_ID = "00000000-0000-0000-0000-000000000001"
_DEFAULT_MATTER_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    # ------------------------------------------------------------------
    # users
    # ------------------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("role", sa.String(50), nullable=False, server_default="reviewer"),
        sa.Column("api_key_hash", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_users_email", "users", ["email"], unique=True)

    # ------------------------------------------------------------------
    # case_matters
    # ------------------------------------------------------------------
    op.create_table(
        "case_matters",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # ------------------------------------------------------------------
    # user_case_matters (join table)
    # ------------------------------------------------------------------
    op.create_table(
        "user_case_matters",
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "matter_id", UUID(as_uuid=True), sa.ForeignKey("case_matters.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("assigned_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("user_id", "matter_id"),
    )

    # ------------------------------------------------------------------
    # Add NULLABLE matter_id FK to existing tables
    # ------------------------------------------------------------------
    op.add_column("jobs", sa.Column("matter_id", UUID(as_uuid=True), sa.ForeignKey("case_matters.id"), nullable=True))
    op.add_column(
        "documents", sa.Column("matter_id", UUID(as_uuid=True), sa.ForeignKey("case_matters.id"), nullable=True)
    )
    op.add_column(
        "chat_messages", sa.Column("matter_id", UUID(as_uuid=True), sa.ForeignKey("case_matters.id"), nullable=True)
    )

    op.create_index("idx_jobs_matter_id", "jobs", ["matter_id"])
    op.create_index("idx_documents_matter_id", "documents", ["matter_id"])
    op.create_index("idx_chat_messages_matter_id", "chat_messages", ["matter_id"])

    # ------------------------------------------------------------------
    # Seed data: admin user + default matter + assignment
    # ------------------------------------------------------------------
    op.execute(
        sa.text(
            "INSERT INTO users (id, email, password_hash, full_name, role) "
            "VALUES (:id, :email, :password_hash, :full_name, :role)"
        ).bindparams(
            id=_ADMIN_ID,
            email="admin@example.com",
            password_hash=_ADMIN_PASSWORD_HASH,
            full_name="System Administrator",
            role="admin",
        )
    )

    op.execute(
        sa.text("INSERT INTO case_matters (id, name, description) VALUES (:id, :name, :description)").bindparams(
            id=_DEFAULT_MATTER_ID,
            name="Default Matter",
            description="Default case matter for development and testing",
        )
    )

    op.execute(
        sa.text("INSERT INTO user_case_matters (user_id, matter_id) VALUES (:user_id, :matter_id)").bindparams(
            user_id=_ADMIN_ID,
            matter_id=_DEFAULT_MATTER_ID,
        )
    )


def downgrade() -> None:
    # Remove seed data
    op.execute(sa.text("DELETE FROM user_case_matters WHERE user_id = :id").bindparams(id=_ADMIN_ID))
    op.execute(sa.text("DELETE FROM case_matters WHERE id = :id").bindparams(id=_DEFAULT_MATTER_ID))
    op.execute(sa.text("DELETE FROM users WHERE id = :id").bindparams(id=_ADMIN_ID))

    # Drop indexes + columns
    op.drop_index("idx_chat_messages_matter_id", table_name="chat_messages")
    op.drop_index("idx_documents_matter_id", table_name="documents")
    op.drop_index("idx_jobs_matter_id", table_name="jobs")

    op.drop_column("chat_messages", "matter_id")
    op.drop_column("documents", "matter_id")
    op.drop_column("jobs", "matter_id")

    # Drop new tables
    op.drop_table("user_case_matters")
    op.drop_table("case_matters")
    op.drop_index("idx_users_email", table_name="users")
    op.drop_table("users")
