"""Tests for CaseService CRUD operations."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest


@pytest.fixture()
def mock_db():
    """Return a mock AsyncSession."""
    db = AsyncMock()
    return db


def _make_mapping_result(rows: list[dict]):
    """Create a mock result that supports .mappings().first() / .all()."""
    mock_result = MagicMock()
    mock_mappings = MagicMock()
    if rows:
        mock_mappings.first.return_value = rows[0]
        mock_mappings.all.return_value = rows
    else:
        mock_mappings.first.return_value = None
        mock_mappings.all.return_value = []
    mock_result.mappings.return_value = mock_mappings
    return mock_result


@pytest.mark.asyncio
async def test_create_case_context(mock_db):
    """CaseService.create_case_context inserts a row and returns correct fields."""
    from app.cases.service import CaseService

    expected_row = {
        "id": UUID("11111111-1111-1111-1111-111111111111"),
        "matter_id": UUID("00000000-0000-0000-0000-000000000001"),
        "anchor_document_id": "raw/abc/complaint.pdf",
        "status": "processing",
        "created_by": UUID("22222222-2222-2222-2222-222222222222"),
        "job_id": "job-123",
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-01T00:00:00",
    }

    mock_db.execute.return_value = _make_mapping_result([expected_row])

    result = await CaseService.create_case_context(
        db=mock_db,
        matter_id="00000000-0000-0000-0000-000000000001",
        anchor_document_id="raw/abc/complaint.pdf",
        created_by="22222222-2222-2222-2222-222222222222",
        job_id="job-123",
    )

    assert result["status"] == "processing"
    assert result["matter_id"] == UUID("00000000-0000-0000-0000-000000000001")
    mock_db.execute.assert_called_once()


@pytest.mark.asyncio
async def test_get_full_context(mock_db):
    """CaseService.get_full_context returns context with claims, parties, and terms."""
    from app.cases.service import CaseService

    context_row = {
        "id": UUID("11111111-1111-1111-1111-111111111111"),
        "matter_id": UUID("00000000-0000-0000-0000-000000000001"),
        "anchor_document_id": "raw/abc/complaint.pdf",
        "status": "draft",
        "created_by": None,
        "confirmed_by": None,
        "confirmed_at": None,
        "job_id": "job-123",
        "timeline": None,
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-01T00:00:00",
    }

    claim_rows = [
        {
            "id": UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            "claim_number": 1,
            "claim_label": "Fraud",
            "claim_text": "Defendant committed fraud",
            "legal_elements": '["intent", "misrepresentation"]',
            "source_pages": "[1, 5]",
            "created_at": "2026-01-01",
            "updated_at": "2026-01-01",
        }
    ]

    party_rows = [
        {
            "id": UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
            "name": "Acme Corp",
            "role": "defendant",
            "description": "A Delaware corporation",
            "aliases": '["the Company"]',
            "entity_id": None,
            "source_pages": "[1]",
            "created_at": "2026-01-01",
            "updated_at": "2026-01-01",
        }
    ]

    term_rows = [
        {
            "id": UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
            "term": "the Agreement",
            "definition": "The Purchase Agreement dated January 1, 2020",
            "entity_id": None,
            "source_pages": "[2]",
            "created_at": "2026-01-01",
            "updated_at": "2026-01-01",
        }
    ]

    # Mock 4 sequential execute calls
    mock_db.execute.side_effect = [
        _make_mapping_result([context_row]),  # get_case_context
        _make_mapping_result(claim_rows),  # claims
        _make_mapping_result(party_rows),  # parties
        _make_mapping_result(term_rows),  # terms
    ]

    result = await CaseService.get_full_context(
        db=mock_db,
        matter_id="00000000-0000-0000-0000-000000000001",
    )

    assert result is not None
    assert result["status"] == "draft"
    assert len(result["claims"]) == 1
    assert result["claims"][0]["claim_label"] == "Fraud"
    assert len(result["parties"]) == 1
    assert result["parties"][0]["name"] == "Acme Corp"
    assert len(result["defined_terms"]) == 1
    assert result["defined_terms"][0]["term"] == "the Agreement"
    assert result["timeline"] == []


@pytest.mark.asyncio
async def test_update_case_context_status(mock_db):
    """CaseService.update_case_context_status sets status and confirmed_by."""
    from app.cases.service import CaseService

    updated_row = {
        "id": UUID("11111111-1111-1111-1111-111111111111"),
        "matter_id": UUID("00000000-0000-0000-0000-000000000001"),
        "status": "confirmed",
        "confirmed_by": UUID("22222222-2222-2222-2222-222222222222"),
        "confirmed_at": "2026-01-01T12:00:00",
        "updated_at": "2026-01-01T12:00:00",
    }

    mock_db.execute.return_value = _make_mapping_result([updated_row])

    result = await CaseService.update_case_context_status(
        db=mock_db,
        context_id="11111111-1111-1111-1111-111111111111",
        status="confirmed",
        confirmed_by="22222222-2222-2222-2222-222222222222",
    )

    assert result is not None
    assert result["status"] == "confirmed"
    assert result["confirmed_by"] == UUID("22222222-2222-2222-2222-222222222222")
