"""Tests for the MinIO webhook endpoint."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture()
async def webhook_client():
    """Async test client with ingestion dependencies mocked."""
    from app import main as main_module

    async def _noop_lifespan(app):
        yield

    with patch.object(main_module, "lifespan", _noop_lifespan):
        test_app = main_module.create_app()

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.flush = AsyncMock()

        from app import dependencies
        from app.common.rate_limit import rate_limit_ingests

        async def mock_get_db():
            yield mock_db

        test_app.dependency_overrides[dependencies.get_db] = mock_get_db
        test_app.dependency_overrides[rate_limit_ingests] = lambda: None

        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            yield ac, mock_db


def _make_s3_event(object_key: str, event_name: str = "s3:ObjectCreated:Put") -> dict:
    """Build a minimal S3 event notification payload."""
    return {
        "Records": [
            {
                "eventName": event_name,
                "s3": {
                    "bucket": {"name": "documents"},
                    "object": {"key": object_key, "size": 1024},
                },
            }
        ]
    }


@pytest.mark.asyncio
async def test_webhook_valid_payload(webhook_client):
    """POST /ingest/webhook with a valid S3 event should return 200 with job_ids."""
    client, mock_db = webhook_client
    fake_job_id = uuid4()
    now = datetime.now(UTC)

    with (
        patch("app.ingestion.router.process_document") as mock_task,
        patch(
            "app.ingestion.service.IngestionService.create_job",
            new_callable=AsyncMock,
            return_value={
                "id": fake_job_id,
                "filename": "test.pdf",
                "status": "pending",
                "stage": "uploading",
                "progress": {},
                "error": None,
                "parent_job_id": None,
                "metadata_": {},
                "created_at": now,
                "updated_at": now,
            },
        ),
    ):
        mock_task.delay = MagicMock()

        response = await client.post(
            "/api/v1/ingest/webhook",
            json=_make_s3_event("raw/batch1/test.pdf"),
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "accepted"
    assert len(body["job_ids"]) == 1
    assert body["total"] == 1
    mock_task.delay.assert_called_once()


@pytest.mark.asyncio
async def test_webhook_empty_records(webhook_client):
    """POST /ingest/webhook with empty Records should return 400."""
    client, _ = webhook_client

    response = await client.post(
        "/api/v1/ingest/webhook",
        json={"Records": []},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_webhook_missing_object_key(webhook_client):
    """POST /ingest/webhook with no object key should return 400."""
    client, _ = webhook_client

    response = await client.post(
        "/api/v1/ingest/webhook",
        json={
            "Records": [
                {
                    "eventName": "s3:ObjectCreated:Put",
                    "s3": {"bucket": {"name": "documents"}, "object": {}},
                }
            ]
        },
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_webhook_skips_non_create_events(webhook_client):
    """POST /ingest/webhook with delete events should return 400 (no actionable events)."""
    client, _ = webhook_client

    response = await client.post(
        "/api/v1/ingest/webhook",
        json=_make_s3_event("raw/test.pdf", event_name="s3:ObjectRemoved:Delete"),
    )
    assert response.status_code == 400
    assert "actionable" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_webhook_multiple_records(webhook_client):
    """POST /ingest/webhook with 3 records should create 3 jobs."""
    client, mock_db = webhook_client
    now = datetime.now(UTC)
    call_count = 0

    async def mock_create_job(**kwargs):
        nonlocal call_count
        call_count += 1
        return {
            "id": uuid4(),
            "filename": kwargs.get("filename", "file.pdf"),
            "status": "pending",
            "stage": "uploading",
            "progress": {},
            "error": None,
            "parent_job_id": None,
            "metadata_": {},
            "created_at": now,
            "updated_at": now,
        }

    payload = {
        "Records": [
            {
                "eventName": "s3:ObjectCreated:Put",
                "s3": {
                    "bucket": {"name": "documents"},
                    "object": {"key": f"raw/batch/file{i}.pdf"},
                },
            }
            for i in range(3)
        ]
    }

    with (
        patch("app.ingestion.router.process_document") as mock_task,
        patch(
            "app.ingestion.service.IngestionService.create_job",
            new_callable=AsyncMock,
            side_effect=mock_create_job,
        ),
    ):
        mock_task.delay = MagicMock()

        response = await client.post("/api/v1/ingest/webhook", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert len(body["job_ids"]) == 3
    assert mock_task.delay.call_count == 3
