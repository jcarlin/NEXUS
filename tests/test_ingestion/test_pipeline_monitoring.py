"""Tests for pipeline monitoring service methods and router endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.ingestion.schemas import (
    FailureAnalysisResponse,
    PipelineThroughputResponse,
)

# ---------------------------------------------------------------------------
# Service tests (mock DB)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_pipeline_throughput():
    """Throughput query returns correct structure."""
    from app.ingestion.service import IngestionService

    mock_row = (5, 2.5, 30.0)
    mock_result = MagicMock()
    mock_result.one.return_value = mock_row

    mock_db = AsyncMock()
    mock_db.execute.return_value = mock_result

    result = await IngestionService.get_pipeline_throughput(db=mock_db)

    assert result["jobs_last_hour"] == 5
    assert result["jobs_per_minute"] == 2.5
    assert result["avg_duration_seconds"] == 30.0
    mock_db.execute.assert_called_once()


@pytest.mark.asyncio
async def test_get_failure_analysis():
    """Failure analysis returns all four sections."""
    from app.ingestion.service import IngestionService

    matter_id = uuid4()
    now = datetime.now(UTC)

    # Mock all 5 DB calls (category, rate, top, stage, totals)
    mock_db = AsyncMock()
    mock_db.execute.side_effect = [
        # category breakdown
        MagicMock(all=lambda: [(("PARSE_ERROR", 3),)]),
        # failure rate
        MagicMock(all=lambda: [((now, 10, 2),)]),
        # top errors
        MagicMock(all=lambda: [(("Invalid PDF", "PARSE_ERROR", 3, now),)]),
        # stage distribution
        MagicMock(all=lambda: [(("parsing", 3),)]),
        # totals
        MagicMock(one=lambda: (5, 20)),
    ]

    # We can't easily mock 5 sequential calls with proper row access,
    # so just verify the method doesn't crash with basic mocking
    mock_db.execute = AsyncMock()
    cat_result = MagicMock()
    cat_result.all.return_value = [("PARSE_ERROR", 3)]
    rate_result = MagicMock()
    rate_result.all.return_value = [(now, 10, 2)]
    top_result = MagicMock()
    top_result.all.return_value = [("Invalid PDF", "PARSE_ERROR", 3, now)]
    stage_result = MagicMock()
    stage_result.all.return_value = [("parsing", 3)]
    totals_result = MagicMock()
    totals_result.one.return_value = (5, 20)

    mock_db.execute.side_effect = [
        cat_result,
        rate_result,
        top_result,
        stage_result,
        totals_result,
    ]

    result = await IngestionService.get_failure_analysis(db=mock_db, matter_id=matter_id, hours=168)

    assert "category_breakdown" in result
    assert "failure_rate" in result
    assert "top_errors" in result
    assert "stage_distribution" in result
    assert result["total_failed"] == 5
    assert result["total_completed"] == 20


@pytest.mark.asyncio
async def test_list_pipeline_events():
    """Events listing returns paginated results."""
    from app.ingestion.service import IngestionService

    event_id = uuid4()
    job_id = uuid4()
    now = datetime.now(UTC)

    mock_db = AsyncMock()

    count_result = MagicMock()
    count_result.scalar_one.return_value = 1

    row = MagicMock()
    row._mapping = {
        "id": event_id,
        "job_id": job_id,
        "event_type": "TASK_COMPLETED",
        "timestamp": now,
        "worker": "worker-1",
        "detail": {},
        "duration_ms": 5000,
        "filename": "test.pdf",
    }
    items_result = MagicMock()
    items_result.all.return_value = [row]

    mock_db.execute.side_effect = [count_result, items_result]

    items, total = await IngestionService.list_pipeline_events(db=mock_db)
    assert total == 1
    assert len(items) == 1


# ---------------------------------------------------------------------------
# Schema validation tests
# ---------------------------------------------------------------------------


def test_throughput_response_defaults():
    resp = PipelineThroughputResponse()
    assert resp.jobs_per_minute == 0.0
    assert resp.jobs_last_hour == 0
    assert resp.avg_duration_seconds == 0.0


def test_failure_analysis_response():
    resp = FailureAnalysisResponse(
        category_breakdown=[{"category": "PARSE_ERROR", "count": 3}],
        failure_rate=[{"timestamp": datetime.now(UTC), "completed": 10, "failed": 2}],
        top_errors=[
            {
                "error_summary": "test",
                "category": "PARSE_ERROR",
                "count": 3,
                "last_seen": datetime.now(UTC),
            }
        ],
        stage_distribution=[{"stage": "parsing", "count": 3}],
        total_failed=5,
        total_completed=20,
    )
    assert resp.total_failed == 5
    assert len(resp.category_breakdown) == 1
