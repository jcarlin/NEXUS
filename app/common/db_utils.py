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


_DOCUMENT_DATE_MIN_YEAR = 1950
_DOCUMENT_DATE_MAX_YEAR_OFFSET = 2  # allow forward-dated contracts up to current_year+2


def is_plausible_document_date(dt: datetime) -> bool:
    """Return True iff *dt* falls within a plausible legal-document date range.

    Rejects dates earlier than 1950 or later than 2 years from today. Catches
    source-metadata corruption (e.g. raw values like "DEC-30-2036" or
    dateutil mis-parsing "1/20/53" as 2053) that would otherwise populate
    the timeline with implausible future/ancient dates.
    """
    now = datetime.now(tz=UTC)
    return _DOCUMENT_DATE_MIN_YEAR <= dt.year <= now.year + _DOCUMENT_DATE_MAX_YEAR_OFFSET


def parse_email_date(raw: str | None) -> datetime | None:
    """Parse an email date string into a timezone-aware datetime.

    Handles RFC 2822, ISO 8601, and Python datetime str representations.
    Returns None for empty, missing, unparseable, or **implausible** values
    (year outside ``[1950, current_year+2]``). The plausibility check
    catches source-metadata corruption that would otherwise populate the
    corpus with year-4501 or year-200 dates.
    """
    if not raw or not raw.strip():
        return None

    raw = raw.strip()
    dt: datetime | None = None

    # 1. RFC 2822 (e.g. "Wed, 12 Feb 2025 16:10:00 +0000")
    try:
        dt = parsedate_to_datetime(raw)
    except (ValueError, TypeError):
        pass

    # 2. ISO 8601 / Python datetime str (e.g. "2025-02-12T16:10:00+00:00")
    if dt is None:
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
        except (ValueError, TypeError):
            dt = None

    # 3. Fallback: dateutil for diverse formats (e.g. "02/12/2025").
    #
    # We pass a sentinel default of year 1 so that if the raw input is
    # missing any component (year, month, day), dateutil fills it with
    # year 1 instead of the current year. That sentinel then fails the
    # plausibility gate below, rejecting partial dates like "July 17",
    # "4/28", or "5:47 PM" that would otherwise silently be dated
    # "today". Full dates with an explicit year continue to parse
    # normally.
    if dt is None:
        try:
            from dateutil.parser import parse as dateutil_parse

            dt = dateutil_parse(raw, default=datetime(1, 1, 1, tzinfo=UTC))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
        except (ValueError, TypeError, ImportError, OverflowError):
            dt = None

    if dt is None:
        return None

    # Plausibility gate — reject obviously bad values.
    if not is_plausible_document_date(dt):
        return None

    return dt


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
