"""Tests for the cases router endpoints."""

from __future__ import annotations

import io
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest


@pytest.mark.asyncio
async def test_setup_case_returns_job_id(client):
    """POST /cases/{matter_id}/setup returns 200 with job_id and case_context_id."""
    matter_id = "00000000-0000-0000-0000-000000000001"

    mock_job_row = {
        "id": UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        "filename": "complaint.pdf",
        "status": "pending",
        "stage": "uploading",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }

    mock_ctx = {
        "id": UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
        "matter_id": UUID(matter_id),
        "anchor_document_id": "raw/test/complaint.pdf",
        "status": "processing",
        "created_by": UUID("00000000-0000-0000-0000-000000000099"),
        "job_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }

    with (
        patch("app.cases.router.get_minio") as mock_minio_factory,
        patch("app.cases.router.CaseService") as mock_service,
        patch("app.ingestion.service.IngestionService.create_job", new_callable=AsyncMock) as mock_create_job,
        patch("app.cases.tasks.run_case_setup") as mock_task,
    ):
        # Mock MinIO
        mock_storage = AsyncMock()
        mock_minio_factory.return_value = mock_storage

        # Mock CaseService
        mock_service.get_case_context = AsyncMock(return_value=None)  # No existing context
        mock_service.create_case_context = AsyncMock(return_value=mock_ctx)

        # Mock IngestionService
        mock_create_job.return_value = mock_job_row

        # Mock Celery task
        mock_task.delay = MagicMock()

        # Upload a file
        file_content = b"fake pdf content"
        response = await client.post(
            f"/api/v1/cases/{matter_id}/setup",
            files={"file": ("complaint.pdf", io.BytesIO(file_content), "application/pdf")},
        )

    assert response.status_code == 200
    data = response.json()
    assert "job_id" in data
    assert "case_context_id" in data
    assert data["status"] == "processing"


@pytest.mark.asyncio
async def test_get_case_context_returns_full(client):
    """GET /cases/{matter_id}/context returns CaseContextResponse with claims/parties/terms."""
    matter_id = "00000000-0000-0000-0000-000000000001"

    mock_full_context = {
        "id": UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
        "matter_id": UUID(matter_id),
        "anchor_document_id": "raw/test/complaint.pdf",
        "status": "draft",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "claims": [
            {
                "id": UUID("11111111-1111-1111-1111-111111111111"),
                "claim_number": 1,
                "claim_label": "Fraud",
                "claim_text": "Fraud claim text",
                "legal_elements": ["intent"],
                "source_pages": [3],
            }
        ],
        "parties": [
            {
                "id": UUID("22222222-2222-2222-2222-222222222222"),
                "name": "Acme Corp",
                "role": "defendant",
                "description": "A company",
                "aliases": ["the Company"],
                "entity_id": None,
                "source_pages": [1],
            }
        ],
        "defined_terms": [
            {
                "id": UUID("33333333-3333-3333-3333-333333333333"),
                "term": "the Agreement",
                "definition": "The Purchase Agreement",
                "entity_id": None,
                "source_pages": [2],
            }
        ],
        "timeline": [{"date": "2020-01-01", "event_text": "Agreement signed", "source_page": 2}],
    }

    with patch("app.cases.router.CaseService") as mock_service:
        mock_service.get_full_context = AsyncMock(return_value=mock_full_context)

        response = await client.get(f"/api/v1/cases/{matter_id}/context")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "draft"
    assert len(data["claims"]) == 1
    assert data["claims"][0]["claim_label"] == "Fraud"
    assert len(data["parties"]) == 1
    assert data["parties"][0]["name"] == "Acme Corp"
    assert len(data["defined_terms"]) == 1
    assert data["defined_terms"][0]["term"] == "the Agreement"
    assert len(data["timeline"]) == 1


@pytest.mark.asyncio
async def test_patch_case_context_updates(client):
    """PATCH /cases/{matter_id}/context with edited claims returns updated context."""
    matter_id = "00000000-0000-0000-0000-000000000001"

    mock_existing_ctx = {
        "id": UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
        "matter_id": UUID(matter_id),
        "status": "draft",
    }

    mock_updated_context = {
        "id": UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
        "matter_id": UUID(matter_id),
        "anchor_document_id": "raw/test/complaint.pdf",
        "status": "confirmed",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T12:00:00+00:00",
        "claims": [
            {
                "id": UUID("44444444-4444-4444-4444-444444444444"),
                "claim_number": 1,
                "claim_label": "Securities Fraud",
                "claim_text": "Updated claim text",
                "legal_elements": ["materiality"],
                "source_pages": [3, 4],
            }
        ],
        "parties": [],
        "defined_terms": [],
        "timeline": [],
    }

    with patch("app.cases.router.CaseService") as mock_service:
        mock_service.get_case_context = AsyncMock(return_value=mock_existing_ctx)
        mock_service.update_case_context_status = AsyncMock(return_value={"status": "confirmed"})
        mock_service.upsert_claims = AsyncMock(return_value=[])
        mock_service.get_full_context = AsyncMock(return_value=mock_updated_context)

        response = await client.patch(
            f"/api/v1/cases/{matter_id}/context",
            json={
                "status": "confirmed",
                "claims": [
                    {
                        "claim_number": 1,
                        "claim_label": "Securities Fraud",
                        "claim_text": "Updated claim text",
                        "legal_elements": ["materiality"],
                        "source_pages": [3, 4],
                    }
                ],
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "confirmed"
    assert len(data["claims"]) == 1
    assert data["claims"][0]["claim_label"] == "Securities Fraud"
