"""Shared database utility functions.

Extracted from duplicated helpers across ingestion, documents, query, and cases modules.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any
from uuid import UUID


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


def parse_email_date(raw: str | None) -> datetime | None:
    """Parse an email date string into a timezone-aware datetime.

    Handles RFC 2822, ISO 8601, and Python datetime str representations.
    Returns None for empty, missing, or unparseable values.
    """
    if not raw or not raw.strip():
        return None

    raw = raw.strip()

    # 1. RFC 2822 (e.g. "Wed, 12 Feb 2025 16:10:00 +0000")
    try:
        return parsedate_to_datetime(raw)
    except (ValueError, TypeError):
        pass

    # 2. ISO 8601 / Python datetime str (e.g. "2025-02-12T16:10:00+00:00")
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    except (ValueError, TypeError):
        pass

    # 3. Fallback: dateutil for diverse formats (e.g. "02/12/2025")
    try:
        from dateutil.parser import parse as dateutil_parse

        dt = dateutil_parse(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    except (ValueError, TypeError, ImportError):
        pass

    return None


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
