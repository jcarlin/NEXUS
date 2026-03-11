"""Tests for IngestionService methods."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.ingestion.service import IngestionService


class TestGetDocumentsForReindex:
    @pytest.mark.asyncio
    async def test_returns_matching_docs(self) -> None:
        doc_id = uuid4()
        matter_id = uuid4()

        db = AsyncMock()
        mock_row = MagicMock()
        mock_row._mapping = {
            "id": doc_id,
            "filename": "test.pdf",
            "minio_path": "raw/abc/test.pdf",
        }
        mock_result = MagicMock()
        mock_result.all.return_value = [mock_row]
        db.execute.return_value = mock_result

        docs = await IngestionService.get_documents_for_reindex(db, [doc_id], matter_id)
        assert len(docs) == 1
        assert docs[0]["filename"] == "test.pdf"
        assert docs[0]["minio_path"] == "raw/abc/test.pdf"

    @pytest.mark.asyncio
    async def test_filters_by_matter_id(self) -> None:
        """Documents from a different matter are not returned."""
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        db.execute.return_value = mock_result

        docs = await IngestionService.get_documents_for_reindex(db, [uuid4()], uuid4())
        assert docs == []

        # Verify matter_id was passed as a parameter
        call_args = db.execute.call_args
        params = call_args[0][1]
        assert "matter_id" in params

    @pytest.mark.asyncio
    async def test_multiple_doc_ids(self) -> None:
        doc_ids = [uuid4(), uuid4(), uuid4()]
        matter_id = uuid4()

        rows = []
        for did in doc_ids[:2]:  # Only 2 of 3 found
            mock_row = MagicMock()
            mock_row._mapping = {
                "id": did,
                "filename": f"{did}.pdf",
                "minio_path": f"raw/{did}/file.pdf",
            }
            rows.append(mock_row)

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = rows
        db.execute.return_value = mock_result

        docs = await IngestionService.get_documents_for_reindex(db, doc_ids, matter_id)
        assert len(docs) == 2
