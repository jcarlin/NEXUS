"""Add error detail columns to jobs table.

New columns: retry_count, worker_hostname, error_category, started_at, completed_at.
These enable the Error Detail Panel in the pipeline monitor UI.

Includes a data migration to backfill error_category for existing failed jobs.

Revision ID: 033
Revises: 032
Create Date: 2026-03-27
"""

import sqlalchemy as sa
from alembic import op

revision = "033"
down_revision = "032"
branch_labels = None
depends_on = None

# ---------------------------------------------------------------------------
# Error classification rules (duplicated from app/ingestion/tasks.py so the
# migration is self-contained and doesn't import application code).
# ---------------------------------------------------------------------------

_CATEGORY_PATTERNS: list[tuple[str, list[str]]] = [
    ("TIMEOUT", ["timed out", "softtimelimitexceeded", "deadline exceeded", "task timed out"]),
    ("OOM", ["memoryerror", "cannot allocate memory", "killed", "oom"]),
    (
        "PARSE_ERROR",
        [
            "parseerror",
            "pdfsyntaxerror",
            "invalid pdf",
            "corrupt",
            "unicodedecodeerror",
            "doclingerror",
            "conversionerror",
        ],
    ),
    (
        "NETWORK",
        [
            "connectionerror",
            "timeouterror",
            "remotedisconnected",
            "econnrefused",
            "connectionrefused",
            "connectionreset",
        ],
    ),
    (
        "LLM_API",
        [
            "anthropic",
            "openai",
            "rate_limit",
            "apierror",
            "insufficient_quota",
            "ratelimit",
            "overloaded",
        ],
    ),
    ("VALIDATION", ["validationerror", "pydantic", "typeerror", "valueerror"]),
    ("STORAGE", ["nosuchkey", "nosuchbucket", "s3error", "minio"]),
]


def _classify_error(error_text: str) -> str:
    lower = error_text.lower()
    for category, patterns in _CATEGORY_PATTERNS:
        for pattern in patterns:
            if pattern in lower:
                return category
    return "UNKNOWN"


def upgrade() -> None:
    op.add_column("jobs", sa.Column("retry_count", sa.Integer(), server_default="0", nullable=False))
    op.add_column("jobs", sa.Column("worker_hostname", sa.Text(), nullable=True))
    op.add_column("jobs", sa.Column("error_category", sa.Text(), nullable=True))
    op.add_column("jobs", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("jobs", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))

    op.create_index(
        "idx_jobs_error_category",
        "jobs",
        ["error_category"],
        postgresql_where="error_category IS NOT NULL",
    )
    op.create_index(
        "idx_jobs_started_at",
        "jobs",
        ["started_at"],
        postgresql_where="started_at IS NOT NULL",
    )

    # --- Backfill error_category for existing failed jobs ---
    conn = op.get_bind()
    # Build CASE expression from category patterns
    when_clauses = []
    for category, patterns in _CATEGORY_PATTERNS:
        conditions = " OR ".join(f"LOWER(error) LIKE '%{pattern}%'" for pattern in patterns)
        when_clauses.append(f"WHEN ({conditions}) THEN '{category}'")

    case_sql = "\n            ".join(when_clauses)
    conn.execute(
        sa.text(f"""
        UPDATE jobs
        SET error_category = CASE
            {case_sql}
            ELSE 'UNKNOWN'
        END
        WHERE status = 'failed'
          AND error IS NOT NULL
          AND error_category IS NULL
    """)
    )

    # Backfill completed_at from updated_at for completed/failed jobs
    conn.execute(
        sa.text("""
            UPDATE jobs SET completed_at = updated_at
            WHERE status IN ('complete', 'failed') AND completed_at IS NULL
        """)
    )


def downgrade() -> None:
    op.drop_index("idx_jobs_started_at", table_name="jobs")
    op.drop_index("idx_jobs_error_category", table_name="jobs")
    op.drop_column("jobs", "completed_at")
    op.drop_column("jobs", "started_at")
    op.drop_column("jobs", "error_category")
    op.drop_column("jobs", "worker_hostname")
    op.drop_column("jobs", "retry_count")
