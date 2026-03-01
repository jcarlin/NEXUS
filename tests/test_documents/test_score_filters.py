"""Tests for hot_doc_score_min and anomaly_score_min filters on GET /documents."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_doc_row(doc_id=None, **overrides) -> dict:
    """Return a dict mimicking a raw DB row from the documents table."""
    base = {
        "id": doc_id or uuid4(),
        "job_id": uuid4(),
        "filename": "report.pdf",
        "document_type": "deposition",
        "page_count": 12,
        "chunk_count": 30,
        "entity_count": 8,
        "minio_path": "raw/abc/report.pdf",
        "file_size_bytes": 204800,
        "content_hash": "sha256-xyz",
        "metadata_": {"source": "batch_001"},
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# hot_doc_score_min filter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_documents_with_hot_doc_score_min(client: AsyncClient) -> None:
    """GET /documents?hot_doc_score_min=0.5 should forward the filter to the service."""
    row = _fake_doc_row(hot_doc_score=0.8)

    with patch(
        "app.documents.service.DocumentService.list_documents",
        new_callable=AsyncMock,
        return_value=([row], 1),
    ) as mock_list:
        response = await client.get("/api/v1/documents?hot_doc_score_min=0.5")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1

    # Verify the filter was passed through to the service
    mock_list.assert_called_once()
    call_kwargs = mock_list.call_args[1]
    assert call_kwargs["hot_doc_score_min"] == 0.5


@pytest.mark.asyncio
async def test_hot_doc_score_min_rejects_out_of_range(client: AsyncClient) -> None:
    """GET /documents?hot_doc_score_min=1.5 should return 422 (out of range)."""
    response = await client.get("/api/v1/documents?hot_doc_score_min=1.5")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_hot_doc_score_min_rejects_negative(client: AsyncClient) -> None:
    """GET /documents?hot_doc_score_min=-0.1 should return 422 (negative)."""
    response = await client.get("/api/v1/documents?hot_doc_score_min=-0.1")
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# anomaly_score_min filter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_documents_with_anomaly_score_min(client: AsyncClient) -> None:
    """GET /documents?anomaly_score_min=0.3 should forward the filter to the service."""
    row = _fake_doc_row(anomaly_score=0.6)

    with patch(
        "app.documents.service.DocumentService.list_documents",
        new_callable=AsyncMock,
        return_value=([row], 1),
    ) as mock_list:
        response = await client.get("/api/v1/documents?anomaly_score_min=0.3")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1

    mock_list.assert_called_once()
    call_kwargs = mock_list.call_args[1]
    assert call_kwargs["anomaly_score_min"] == 0.3


@pytest.mark.asyncio
async def test_anomaly_score_min_rejects_out_of_range(client: AsyncClient) -> None:
    """GET /documents?anomaly_score_min=2.0 should return 422 (out of range)."""
    response = await client.get("/api/v1/documents?anomaly_score_min=2.0")
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Combined filters
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_documents_with_both_score_filters(client: AsyncClient) -> None:
    """GET /documents with both score filters passes both to the service."""
    row = _fake_doc_row(hot_doc_score=0.9, anomaly_score=0.7)

    with patch(
        "app.documents.service.DocumentService.list_documents",
        new_callable=AsyncMock,
        return_value=([row], 1),
    ) as mock_list:
        response = await client.get("/api/v1/documents?hot_doc_score_min=0.5&anomaly_score_min=0.3")

    assert response.status_code == 200
    mock_list.assert_called_once()
    call_kwargs = mock_list.call_args[1]
    assert call_kwargs["hot_doc_score_min"] == 0.5
    assert call_kwargs["anomaly_score_min"] == 0.3


@pytest.mark.asyncio
async def test_list_documents_without_score_filters(client: AsyncClient) -> None:
    """GET /documents without score filters passes None for both."""
    with patch(
        "app.documents.service.DocumentService.list_documents",
        new_callable=AsyncMock,
        return_value=([], 0),
    ) as mock_list:
        response = await client.get("/api/v1/documents")

    assert response.status_code == 200
    mock_list.assert_called_once()
    call_kwargs = mock_list.call_args[1]
    assert call_kwargs["hot_doc_score_min"] is None
    assert call_kwargs["anomaly_score_min"] is None
