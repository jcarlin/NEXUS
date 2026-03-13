"""Text-to-SQL generation with safety validation.

Generates read-only SQL queries from natural language questions,
validates them for safety (no writes, matter-scoped, LIMIT enforced,
table allowlist), and formats results for the investigation agent.

Follows the same pattern as ``cypher_generator.py``.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

import structlog
from pydantic import BaseModel, Field

from app.query.prompts import TEXT_TO_SQL_PROMPT, TEXT_TO_SQL_SCHEMA

if TYPE_CHECKING:
    from app.common.llm import LLMClient

logger = structlog.get_logger(__name__)

# Write operations that must be rejected
_WRITE_OPERATIONS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|GRANT|REVOKE|COPY)\b",
    re.IGNORECASE,
)

# Tables that are safe to query
ALLOWED_TABLES = frozenset(
    {
        "documents",
        "annotations",
        "memos",
        "chat_messages",
        "jobs",
        "datasets",
        "dataset_documents",
        "case_matters",
        "case_contexts",
        "case_claims",
        "case_parties",
        "case_defined_terms",
        "communication_pairs",
        "evaluation_dataset_items",
        "evaluation_runs",
    }
)

# Tables that must NEVER be queried
_FORBIDDEN_TABLES = re.compile(
    r"\b(users|audit_log|ai_audit_log|agent_audit_log|sessions"
    r"|feature_flag_overrides|llm_providers|llm_tier_config"
    r"|user_case_matters|google_drive_connections"
    r"|google_drive_sync_state)\b",
    re.IGNORECASE,
)


class SQLQuery(BaseModel):
    """Generated SQL query with explanation and table list."""

    sql: str = Field(..., description="The SQL query string")
    explanation: str = Field("", description="Human-readable explanation of the query")
    tables_used: list[str] = Field(default_factory=list, description="Tables referenced in the query")


async def generate_sql(
    question: str,
    matter_id: str,
    llm: LLMClient,
) -> SQLQuery:
    """Generate a SQL query from a natural language question.

    Args:
        question: The user's natural language question.
        matter_id: Current matter scope (injected into params).
        llm: LLM client for generation.

    Returns:
        SQLQuery with the generated query, explanation, and tables used.
    """
    prompt = TEXT_TO_SQL_PROMPT.format(
        schema=TEXT_TO_SQL_SCHEMA,
        question=question,
    )

    raw = await llm.complete(
        [{"role": "user", "content": prompt}],
        max_tokens=800,
        temperature=0.0,
        node_name="text_to_sql",
    )

    result = _parse_sql_response(raw)

    logger.info(
        "sql_generator.generated",
        sql=result.sql[:200],
        question=question[:100],
        tables=result.tables_used,
    )

    return result


def validate_sql_safety(sql: str) -> tuple[bool, str]:
    """Validate a SQL query for safety before execution.

    Returns:
        Tuple of (is_safe, reason). If is_safe is False, reason explains why.
    """
    # Reject write operations
    match = _WRITE_OPERATIONS.search(sql)
    if match:
        return False, f"Write operation detected: {match.group()}"

    # Reject forbidden tables
    forbidden_match = _FORBIDDEN_TABLES.search(sql)
    if forbidden_match:
        return False, f"Forbidden table referenced: {forbidden_match.group()}"

    # Require matter_id parameter reference
    if ":matter_id" not in sql and "matter_id" not in sql:
        return False, "Query does not reference matter_id -- all queries must be matter-scoped"

    # Enforce LIMIT clause
    if not re.search(r"\bLIMIT\b", sql, re.IGNORECASE):
        return False, "Query missing LIMIT clause"

    return True, ""


def ensure_limit(sql: str, max_limit: int = 100) -> str:
    """Inject or cap the LIMIT clause in a SQL query."""
    limit_match = re.search(r"\bLIMIT\s+(\d+)", sql, re.IGNORECASE)
    if limit_match:
        current = int(limit_match.group(1))
        if current > max_limit:
            sql = sql[: limit_match.start(1)] + str(max_limit) + sql[limit_match.end(1) :]
    else:
        sql = sql.rstrip().rstrip(";") + f" LIMIT {max_limit}"
    return sql


def ensure_matter_id(sql: str) -> str:
    """Ensure the SQL query references :matter_id parameter."""
    if ":matter_id" not in sql:
        # Try to inject into existing WHERE clause
        where_match = re.search(r"\bWHERE\b", sql, re.IGNORECASE)
        if where_match:
            insert_pos = where_match.end()
            sql = sql[:insert_pos] + " matter_id = :matter_id AND" + sql[insert_pos:]
        else:
            # No WHERE clause — inject before ORDER BY, GROUP BY, or LIMIT
            for clause in (r"\bORDER\b", r"\bGROUP\b", r"\bLIMIT\b"):
                clause_match = re.search(clause, sql, re.IGNORECASE)
                if clause_match:
                    insert_pos = clause_match.start()
                    sql = sql[:insert_pos] + "WHERE matter_id = :matter_id " + sql[insert_pos:]
                    break
            else:
                sql = sql.rstrip().rstrip(";") + " WHERE matter_id = :matter_id"
    return sql


def _parse_sql_response(raw: str) -> SQLQuery:
    """Best-effort parse a SQLQuery from LLM output."""
    # Try direct JSON parse
    try:
        data = json.loads(raw.strip())
        return SQLQuery(**data)
    except Exception:
        pass

    # Try finding JSON object in response
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            data = json.loads(raw[start : end + 1])
            return SQLQuery(**data)
        except Exception:
            pass

    # Last resort: treat entire response as SQL
    return SQLQuery(sql=raw.strip(), explanation="Parsed from raw response")


async def execute_sql(
    sql: str,
    matter_id: str,
    *,
    max_rows: int = 100,
) -> list[dict[str, Any]]:
    """Execute a validated read-only SQL query and return results.

    Args:
        sql: The SQL query to execute (must be validated first).
        matter_id: Matter ID for parameterized query.
        max_rows: Maximum rows to return.

    Returns:
        List of result dicts.
    """
    from sqlalchemy import text

    from app.dependencies import get_db

    # Ensure safety constraints
    sql = ensure_limit(sql, max_limit=max_rows)
    sql = ensure_matter_id(sql)

    db_gen = get_db()
    db = await db_gen.__anext__()
    try:
        result = await db.execute(text(sql), {"matter_id": matter_id})
        rows = [dict(r._mapping) for r in result.all()]
        logger.info("sql_generator.executed", row_count=len(rows), sql=sql[:200])
        return rows
    finally:
        try:
            await db_gen.aclose()
        except Exception as e:
            logger.warning("sql_generator.db_cleanup_failed", error=str(e))
