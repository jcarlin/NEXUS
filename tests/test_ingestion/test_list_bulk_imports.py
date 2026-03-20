"""Tests for GET /api/v1/bulk-imports endpoint."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_bulk_imports_empty(client: AsyncClient) -> None:
    """GET /bulk-imports should return empty paginated response."""
    with patch(
        "app.ingestion.service.IngestionService.list_bulk_imports",
        new_callable=AsyncMock,
        return_value=([], 0),
    ):
        response = await client.get("/api/v1/bulk-imports")

    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["total"] == 0
    assert body["offset"] == 0
    assert body["limit"] == 50


@pytest.mark.asyncio
async def test_list_bulk_imports_with_data(client: AsyncClient) -> None:
    """GET /bulk-imports should return bulk import jobs."""
    import_id = uuid4()
    now = datetime.now(UTC)
    mock_row = {
        "id": import_id,
        "matter_id": UUID("00000000-0000-0000-0000-000000000001"),
        "adapter_type": "directory",
        "source_path": "/tmp/test",
        "status": "complete",
        "total_documents": 50,
        "processed_documents": 48,
        "failed_documents": 2,
        "skipped_documents": 0,
        "error": None,
        "created_at": now,
        "updated_at": now,
        "completed_at": now,
    }

    with patch(
        "app.ingestion.service.IngestionService.list_bulk_imports",
        new_callable=AsyncMock,
        return_value=([mock_row], 1),
    ):
        response = await client.get("/api/v1/bulk-imports")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["status"] == "complete"
    assert item["source_path"] == "/tmp/test"
    assert item["total_documents"] == 50
    assert item["processed_documents"] == 48
    assert item["failed_documents"] == 2


@pytest.mark.asyncio
async def test_list_bulk_imports_pagination(client: AsyncClient) -> None:
    """GET /bulk-imports should respect offset and limit params."""
    with patch(
        "app.ingestion.service.IngestionService.list_bulk_imports",
        new_callable=AsyncMock,
        return_value=([], 0),
    ) as mock_list:
        response = await client.get("/api/v1/bulk-imports?offset=10&limit=25")

    assert response.status_code == 200
    # Verify correct params were passed to service
    call_kwargs = mock_list.call_args
    assert call_kwargs.kwargs["offset"] == 10
    assert call_kwargs.kwargs["limit"] == 25
