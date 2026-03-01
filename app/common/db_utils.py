"""Shared database utility functions.

Extracted from duplicated helpers across ingestion, documents, query, and cases modules.
"""

from __future__ import annotations

import json
from datetime import datetime
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
