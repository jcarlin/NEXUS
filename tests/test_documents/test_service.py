"""Tests for DocumentService (raw SQL CRUD against the documents table).

All DB interactions are mocked via ``AsyncMock`` — no real Postgres needed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.documents.service import DocumentService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_fake_row(overrides: dict | None = None) -> MagicMock:
    """Create a fake SQLAlchemy Row with a ``_mapping`` attribute."""
    base = {
        "id": uuid4(),
        "job_id": uuid4(),
        "filename": "test.pdf",
        "document_type": "deposition",
        "page_count": 10,
        "chunk_count": 25,
        "entity_count": 5,
        "minio_path": "raw/abc/test.pdf",
        "file_size_bytes": 102400,
        "content_hash": "sha256-abc123",
        "metadata_": {},
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    if overrides:
        base.update(overrides)

    row = MagicMock()
    row._mapping = base
    return row


def _mock_db() -> AsyncMock:
    """Return a mock AsyncSession."""
    return AsyncMock()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_documents_empty() -> None:
    """list_documents returns ([], 0) when no rows exist."""
    db = _mock_db()

    # COUNT query
    count_result = MagicMock()
    count_result.scalar_one.return_value = 0

    # SELECT query
    select_result = MagicMock()
    select_result.all.return_value = []

    db.execute = AsyncMock(side_effect=[count_result, select_result])

    items, total = await DocumentService.list_documents(db)
    assert items == []
    assert total == 0


@pytest.mark.asyncio
async def test_list_documents_with_type_filter() -> None:
    """list_documents passes document_type filter into the SQL query."""
    db = _mock_db()

    row = _make_fake_row({"document_type": "email"})

    count_result = MagicMock()
    count_result.scalar_one.return_value = 1

    select_result = MagicMock()
    select_result.all.return_value = [row]

    db.execute = AsyncMock(side_effect=[count_result, select_result])

    items, total = await DocumentService.list_documents(db, document_type="email")
    assert total == 1
    assert len(items) == 1
    assert items[0]["document_type"] == "email"

    # Verify the document_type param was passed to the query
    call_args = db.execute.call_args_list[0]
    params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("params", {})
    assert params.get("document_type") == "email"


@pytest.mark.asyncio
async def test_get_document_found() -> None:
    """get_document returns a dict when the document exists."""
    db = _mock_db()
    doc_id = uuid4()
    row = _make_fake_row({"id": doc_id})

    result = MagicMock()
    result.first.return_value = row
    db.execute = AsyncMock(return_value=result)

    doc = await DocumentService.get_document(db, doc_id)
    assert doc is not None
    assert doc["id"] == doc_id
    assert "filename" in doc
    assert "minio_path" in doc


@pytest.mark.asyncio
async def test_get_document_not_found() -> None:
    """get_document returns None when the document does not exist."""
    db = _mock_db()

    result = MagicMock()
    result.first.return_value = None
    db.execute = AsyncMock(return_value=result)

    doc = await DocumentService.get_document(db, uuid4())
    assert doc is None


@pytest.mark.asyncio
async def test_get_document_by_job() -> None:
    """get_document_by_job looks up a document by its parent job_id."""
    db = _mock_db()
    job_id = uuid4()
    row = _make_fake_row({"job_id": job_id})

    result = MagicMock()
    result.first.return_value = row
    db.execute = AsyncMock(return_value=result)

    doc = await DocumentService.get_document_by_job(db, job_id)
    assert doc is not None
    assert doc["job_id"] == job_id


@pytest.mark.asyncio
async def test_delete_document() -> None:
    """delete_document returns True when a row is actually deleted."""
    db = _mock_db()

    result = MagicMock()
    result.rowcount = 1
    db.execute = AsyncMock(return_value=result)

    deleted = await DocumentService.delete_document(db, uuid4())
    assert deleted is True


@pytest.mark.asyncio
async def test_delete_document_not_found() -> None:
    """delete_document returns False when no matching row exists."""
    db = _mock_db()

    result = MagicMock()
    result.rowcount = 0
    db.execute = AsyncMock(return_value=result)

    deleted = await DocumentService.delete_document(db, uuid4())
    assert deleted is False
