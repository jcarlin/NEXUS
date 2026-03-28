"""Tests for parse_email_date in app.common.db_utils."""

from __future__ import annotations

from datetime import UTC, datetime, timezone

import pytest

from app.common.db_utils import parse_email_date


@pytest.mark.parametrize(
    "raw, expected",
    [
        # RFC 2822 standard
        (
            "Wed, 12 Feb 2025 16:10:00 +0000",
            datetime(2025, 2, 12, 16, 10, 0, tzinfo=UTC),
        ),
        # RFC 2822 with offset
        (
            "Mon, 10 Mar 2025 09:30:00 -0500",
            datetime(2025, 3, 10, 9, 30, 0, tzinfo=timezone(offset=__import__("datetime").timedelta(hours=-5))),
        ),
        # ISO 8601 with timezone
        (
            "2025-02-12T16:10:00+00:00",
            datetime(2025, 2, 12, 16, 10, 0, tzinfo=UTC),
        ),
        # ISO 8601 with Z
        (
            "2025-02-12T16:10:00Z",
            datetime(2025, 2, 12, 16, 10, 0, tzinfo=UTC),
        ),
        # ISO 8601 date-only (naive -> UTC)
        (
            "2025-02-12",
            datetime(2025, 2, 12, 0, 0, 0, tzinfo=UTC),
        ),
        # Python datetime str
        (
            "2025-02-12 16:10:00+00:00",
            datetime(2025, 2, 12, 16, 10, 0, tzinfo=UTC),
        ),
        # EDRM/Concordance format (dateutil fallback)
        (
            "02/12/2025",
            datetime(2025, 2, 12, 0, 0, 0, tzinfo=UTC),
        ),
        # Naive datetime string -> UTC
        (
            "2025-02-12 16:10:00",
            datetime(2025, 2, 12, 16, 10, 0, tzinfo=UTC),
        ),
    ],
    ids=[
        "rfc2822_utc",
        "rfc2822_offset",
        "iso8601_tz",
        "iso8601_z",
        "iso8601_date_only",
        "python_datetime_str",
        "edrm_slash_format",
        "naive_to_utc",
    ],
)
def test_parse_email_date_valid(raw: str, expected: datetime):
    result = parse_email_date(raw)
    assert result is not None
    assert result == expected
    assert result.tzinfo is not None


@pytest.mark.parametrize(
    "raw",
    [None, "", "  ", "not a date", "???"],
    ids=["none", "empty", "whitespace", "garbage", "symbols"],
)
def test_parse_email_date_returns_none(raw: str | None):
    assert parse_email_date(raw) is None


def test_parse_email_date_always_tz_aware():
    """Every parseable result must be timezone-aware."""
    samples = [
        "Wed, 12 Feb 2025 16:10:00 +0000",
        "2025-02-12T16:10:00Z",
        "2025-02-12",
        "02/12/2025",
    ]
    for s in samples:
        result = parse_email_date(s)
        assert result is not None, f"Failed to parse: {s}"
        assert result.tzinfo is not None, f"Naive result for: {s}"
