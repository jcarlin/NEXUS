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


# ---------------------------------------------------------------------------
# Plausibility gate: reject out-of-range dates that would otherwise populate
# the corpus with source-metadata corruption (e.g. year 4501 from dateutil
# misinterpretation, or literal "DEC-30-2036").
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        # Literal corrupted source metadata values seen in production corpus
        "DEC-30-2036",
        "March 29, 2111",
        "4501-01-01",
        "0200-01-07",
        # 2-digit year that dateutil would parse as a future year (e.g. 2053)
        # — note: dateutil default behaviour varies; this tests the gate.
    ],
    ids=["year_2036", "year_2111", "year_4501", "year_200"],
)
def test_parse_email_date_rejects_implausible_years(raw: str):
    """Dates outside [1950, current_year+2] must be rejected as None."""
    result = parse_email_date(raw)
    assert result is None, f"Implausible date {raw!r} should have been rejected, got {result!r}"


def test_is_plausible_document_date():
    """The plausibility helper accepts the legal-doc range and rejects outside."""
    from datetime import UTC, datetime

    from app.common.db_utils import is_plausible_document_date

    now = datetime.now(tz=UTC)

    # Plausible: within [1950, current_year + 2]
    assert is_plausible_document_date(datetime(1950, 1, 1, tzinfo=UTC))
    assert is_plausible_document_date(datetime(2005, 6, 15, tzinfo=UTC))
    assert is_plausible_document_date(datetime(now.year, 1, 1, tzinfo=UTC))
    assert is_plausible_document_date(datetime(now.year + 2, 12, 31, tzinfo=UTC))

    # Implausible: before 1950 or more than 2 years ahead
    assert not is_plausible_document_date(datetime(1949, 12, 31, tzinfo=UTC))
    assert not is_plausible_document_date(datetime(1900, 1, 1, tzinfo=UTC))
    assert not is_plausible_document_date(datetime(now.year + 3, 1, 1, tzinfo=UTC))
    assert not is_plausible_document_date(datetime(4501, 1, 1, tzinfo=UTC))
