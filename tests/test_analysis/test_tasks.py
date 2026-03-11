"""Tests for analysis Celery tasks with job tracking."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestScanDocumentSentimentJobTracking:
    """Verify scan_document_sentiment creates and updates a job record."""

    @patch("app.analysis.tasks._get_sync_engine")
    @patch("app.analysis.tasks._create_job_sync")
    @patch("app.analysis.tasks._update_stage")
    def test_creates_job_on_start(self, mock_update, mock_create_job, mock_engine):
        mock_engine.return_value = MagicMock()
        mock_create_job.return_value = "job-sent-1"

        with (
            patch("app.config.Settings"),
            patch("qdrant_client.QdrantClient") as mock_qdrant_cls,
        ):
            mock_qdrant = MagicMock()
            mock_qdrant_cls.return_value = mock_qdrant
            mock_qdrant.scroll.return_value = ([], None)  # No chunks → skipped

            from app.analysis.tasks import scan_document_sentiment

            result = scan_document_sentiment("doc-abc", matter_id="m-1")

        assert result["status"] == "skipped"
        mock_create_job.assert_called_once_with(
            mock_engine.return_value,
            "m-1",
            "analysis_sentiment",
            "Sentiment: doc-abc...",
        )
        # Should have updated to loading_chunks then complete (skipped)
        stage_calls = [c.args[2] for c in mock_update.call_args_list]
        assert "loading_chunks" in stage_calls
        assert "complete" in stage_calls

    @patch("app.analysis.tasks._get_sync_engine")
    @patch("app.analysis.tasks._create_job_sync")
    @patch("app.analysis.tasks._update_stage")
    def test_marks_failed_on_error(self, mock_update, mock_create_job, mock_engine):
        mock_engine.return_value = MagicMock()
        mock_create_job.return_value = "job-sent-2"

        with (
            patch("app.config.Settings"),
            patch("qdrant_client.QdrantClient") as mock_qdrant_cls,
        ):
            mock_qdrant = MagicMock()
            mock_qdrant_cls.return_value = mock_qdrant
            mock_qdrant.scroll.side_effect = RuntimeError("Qdrant down")

            from app.analysis.tasks import scan_document_sentiment

            with pytest.raises(Exception):
                scan_document_sentiment("doc-xyz", matter_id="m-2")

        failed_calls = [c for c in mock_update.call_args_list if c.args[3] == "failed"]
        assert len(failed_calls) == 1


class TestScanMatterHotDocsJobTracking:
    """Verify scan_matter_hot_docs creates a parent job and dispatches."""

    @patch("app.analysis.tasks._get_sync_engine")
    @patch("app.analysis.tasks._create_job_sync")
    @patch("app.analysis.tasks._update_stage")
    @patch("app.analysis.tasks.scan_document_sentiment")
    def test_creates_parent_job_and_dispatches(self, mock_sentiment, mock_update, mock_create_job, mock_engine):
        engine = MagicMock()
        mock_engine.return_value = engine
        mock_create_job.return_value = "job-scan-1"

        # Mock DB query for unscored docs
        mock_rows = [MagicMock(id="doc-1"), MagicMock(id="doc-2")]
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.all.return_value = mock_rows
        mock_conn.execute.return_value = mock_result
        engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        mock_sentiment.delay = MagicMock()

        from app.analysis.tasks import scan_matter_hot_docs

        result = scan_matter_hot_docs("m-1")

        assert result["dispatched"] == 2
        mock_create_job.assert_called_once()
        call_args = mock_create_job.call_args
        assert call_args.args[2] == "analysis_matter_scan"
        assert "2 documents" in call_args.args[3]

        # Should have dispatched sentiment tasks
        assert mock_sentiment.delay.call_count == 2

        # Should complete with progress
        complete_calls = [c for c in mock_update.call_args_list if c.args[2] == "complete"]
        assert len(complete_calls) == 1
        assert complete_calls[0].kwargs.get("progress", {}).get("dispatched") == 2
