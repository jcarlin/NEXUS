"""Tests for the document health check endpoint and service method.

Verifies that the health check correctly compares PostgreSQL chunk_count
against Qdrant indexed point counts and returns accurate statuses.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MATTER_ID = uuid4()


def _fake_db_row(doc_id=None, job_id=None, filename="report.pdf", chunk_count=30):
    """Mimic a raw DB row from the documents table."""
    _doc_id = doc_id or uuid4()
    _job_id = job_id or uuid4()
    mapping = {
        "id": _doc_id,
        "job_id": _job_id,
        "filename": filename,
        "chunk_count": chunk_count,
    }
    row = MagicMock()
    row._mapping = mapping
    return row


# ---------------------------------------------------------------------------
# Service: check_ingestion_health
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_check_all_healthy() -> None:
    """When Qdrant has all expected chunks, every doc is 'healthy'."""
    from app.documents.service import DocumentService

    job_id = uuid4()
    row = _fake_db_row(job_id=job_id, chunk_count=30)

    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.all.return_value = [row]
    db.execute.return_value = result_mock

    qdrant = MagicMock()
    qdrant.count_points_by_doc_ids.return_value = {str(job_id): 30}

    items = await DocumentService.check_ingestion_health(db, qdrant, MATTER_ID)

    assert len(items) == 1
    assert items[0]["status"] == "healthy"
    assert items[0]["indexed_chunks"] == 30
    assert items[0]["expected_chunks"] == 30


@pytest.mark.asyncio
async def test_health_check_missing() -> None:
    """When Qdrant has 0 points for a doc, status is 'missing'."""
    from app.documents.service import DocumentService

    job_id = uuid4()
    row = _fake_db_row(job_id=job_id, chunk_count=25)

    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.all.return_value = [row]
    db.execute.return_value = result_mock

    qdrant = MagicMock()
    qdrant.count_points_by_doc_ids.return_value = {str(job_id): 0}

    items = await DocumentService.check_ingestion_health(db, qdrant, MATTER_ID)

    assert len(items) == 1
    assert items[0]["status"] == "missing"
    assert items[0]["indexed_chunks"] == 0


@pytest.mark.asyncio
async def test_health_check_partial() -> None:
    """When Qdrant has fewer points than expected, status is 'partial'."""
    from app.documents.service import DocumentService

    job_id = uuid4()
    row = _fake_db_row(job_id=job_id, chunk_count=30)

    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.all.return_value = [row]
    db.execute.return_value = result_mock

    qdrant = MagicMock()
    qdrant.count_points_by_doc_ids.return_value = {str(job_id): 15}

    items = await DocumentService.check_ingestion_health(db, qdrant, MATTER_ID)

    assert len(items) == 1
    assert items[0]["status"] == "partial"
    assert items[0]["indexed_chunks"] == 15
    assert items[0]["expected_chunks"] == 30


@pytest.mark.asyncio
async def test_health_check_empty_matter() -> None:
    """No docs with chunk_count > 0 returns empty list."""
    from app.documents.service import DocumentService

    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.all.return_value = []
    db.execute.return_value = result_mock

    qdrant = MagicMock()

    items = await DocumentService.check_ingestion_health(db, qdrant, MATTER_ID)

    assert items == []
    qdrant.count_points_by_doc_ids.assert_not_called()


@pytest.mark.asyncio
async def test_health_check_multiple_docs() -> None:
    """Mixed statuses across multiple documents."""
    from app.documents.service import DocumentService

    j1, j2, j3 = uuid4(), uuid4(), uuid4()
    rows = [
        _fake_db_row(job_id=j1, filename="healthy.pdf", chunk_count=10),
        _fake_db_row(job_id=j2, filename="missing.pdf", chunk_count=20),
        _fake_db_row(job_id=j3, filename="partial.pdf", chunk_count=15),
    ]

    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.all.return_value = rows
    db.execute.return_value = result_mock

    qdrant = MagicMock()
    qdrant.count_points_by_doc_ids.return_value = {
        str(j1): 10,
        str(j2): 0,
        str(j3): 7,
    }

    items = await DocumentService.check_ingestion_health(db, qdrant, MATTER_ID)

    status_map = {item["filename"]: item["status"] for item in items}
    assert status_map["healthy.pdf"] == "healthy"
    assert status_map["missing.pdf"] == "missing"
    assert status_map["partial.pdf"] == "partial"


# ---------------------------------------------------------------------------
# Router: GET /documents/health
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_endpoint_returns_200(client: AsyncClient) -> None:
    """GET /documents/health returns aggregated health data."""
    with patch(
        "app.documents.service.DocumentService.check_ingestion_health",
        new_callable=AsyncMock,
        return_value=[
            {
                "doc_id": uuid4(),
                "filename": "good.pdf",
                "expected_chunks": 10,
                "indexed_chunks": 10,
                "status": "healthy",
            },
            {
                "doc_id": uuid4(),
                "filename": "bad.pdf",
                "expected_chunks": 20,
                "indexed_chunks": 0,
                "status": "missing",
            },
        ],
    ):
        response = await client.get("/api/v1/documents/health")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["healthy"] == 1
    assert body["missing"] == 1
    assert body["partial"] == 0
    assert len(body["documents"]) == 2
