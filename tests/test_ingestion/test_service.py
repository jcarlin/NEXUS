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


class TestCreateJob:
    @pytest.mark.asyncio
    async def test_create_job_default_task_type(self) -> None:
        """create_job defaults to task_type='ingestion'."""
        db = AsyncMock()
        db.flush = AsyncMock()

        result = await IngestionService.create_job(db, filename="test.pdf", minio_path="raw/123/test.pdf")
        assert result["task_type"] == "ingestion"
        assert result["label"] is None
        assert result["filename"] == "test.pdf"

    @pytest.mark.asyncio
    async def test_create_job_custom_task_type(self) -> None:
        """create_job with explicit task_type and label."""
        db = AsyncMock()
        db.flush = AsyncMock()

        result = await IngestionService.create_job(
            db,
            task_type="entity_resolution",
            label="Entity resolution: person",
            matter_id=uuid4(),
        )
        assert result["task_type"] == "entity_resolution"
        assert result["label"] == "Entity resolution: person"
        assert result["filename"] is None

    @pytest.mark.asyncio
    async def test_create_job_nullable_filename(self) -> None:
        """Non-ingestion jobs can have filename=None."""
        db = AsyncMock()
        db.flush = AsyncMock()

        result = await IngestionService.create_job(
            db,
            task_type="reprocess_neo4j",
            label="Neo4j reindex: 5 docs",
        )
        assert result["filename"] is None

    @pytest.mark.asyncio
    async def test_create_job_includes_task_type_in_sql(self) -> None:
        """Verify the SQL INSERT includes task_type and label params."""
        db = AsyncMock()
        db.flush = AsyncMock()

        await IngestionService.create_job(db, task_type="case_setup", label="Case setup: complaint.pdf")

        # Check the params passed to db.execute
        call_args = db.execute.call_args
        params = call_args[0][1]
        assert params["task_type"] == "case_setup"
        assert params["label"] == "Case setup: complaint.pdf"


class TestListJobs:
    @pytest.mark.asyncio
    async def test_list_jobs_with_task_type_filter(self) -> None:
        """list_jobs with task_type filter includes it in WHERE clause."""
        db = AsyncMock()

        # Mock count query
        mock_count_result = MagicMock()
        mock_count_result.scalar_one.return_value = 0

        # Mock rows query
        mock_rows_result = MagicMock()
        mock_rows_result.all.return_value = []

        db.execute.side_effect = [mock_count_result, mock_rows_result]

        items, total = await IngestionService.list_jobs(db, task_type="entity_resolution", matter_id=uuid4())
        assert total == 0
        assert items == []

        # Verify task_type was in the params
        first_call_params = db.execute.call_args_list[0][0][1]
        assert first_call_params["task_type"] == "entity_resolution"

    @pytest.mark.asyncio
    async def test_list_jobs_without_task_type_returns_all(self) -> None:
        """list_jobs without task_type filter does not constrain by task_type."""
        db = AsyncMock()

        mock_count_result = MagicMock()
        mock_count_result.scalar_one.return_value = 0
        mock_rows_result = MagicMock()
        mock_rows_result.all.return_value = []
        db.execute.side_effect = [mock_count_result, mock_rows_result]

        await IngestionService.list_jobs(db, matter_id=uuid4())

        first_call_params = db.execute.call_args_list[0][0][1]
        assert "task_type" not in first_call_params
