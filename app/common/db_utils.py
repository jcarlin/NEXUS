"""Shared database utility functions.

Extracted from duplicated helpers across ingestion, documents, query, and cases modules.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import UUID


def build_where_clause(
    filters: dict[str, tuple[str, Any]],
) -> tuple[str, dict[str, Any]]:
    """Build a parameterized WHERE clause from optional filters.

    Each entry in *filters* maps a parameter name to ``(sql_expr, value)``.
    Entries with ``None`` values are silently skipped.

    Returns ``(where_sql, params)`` where *where_sql* is either an empty
    string (no active filters) or ``"WHERE <cond1> AND <cond2> ..."``.

    Example::

        where_sql, params = build_where_clause({
            "user_id": ("user_id = :user_id", user_id),
            "date_from": ("created_at >= :date_from", date_from),
        })
    """
    clauses: list[str] = []
    params: dict[str, Any] = {}
    for param_name, (expr, value) in filters.items():
        if value is not None:
            clauses.append(expr)
            params[param_name] = value
    where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    return where_sql, params


def parse_jsonb(val: Any) -> list[Any]:
    """Safely parse a JSONB column that may be a string, list, or None."""
    if val is None:
        return []
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        try:
            parsed = json.loads(val)
            return list(parsed) if isinstance(parsed, list) else []
        except (json.JSONDecodeError, TypeError):
            return []
    return []


def row_to_dict(row) -> dict:
    """Convert a SQLAlchemy Row (from text query) into a plain dict.

    UUID and datetime values are preserved as-is so the dict
    can be passed directly into Pydantic response models.
    """
    raw = dict(row._mapping)
    for key, value in raw.items():
        if isinstance(value, UUID):
            raw[key] = value
        if isinstance(value, datetime):
            raw[key] = value
    return raw
