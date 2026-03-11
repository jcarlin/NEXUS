"""Tests for entity resolution Celery tasks with job tracking."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestResolveEntitiesJobTracking:
    """Verify resolve_entities creates and updates a job record."""

    @patch("app.entities.tasks._get_sync_engine")
    @patch("app.entities.tasks._run_resolution")
    @patch("app.entities.tasks._create_job_sync")
    @patch("app.entities.tasks._update_stage")
    def test_creates_job_and_updates_stages(self, mock_update, mock_create_job, mock_run, mock_engine):
        mock_engine.return_value = MagicMock()
        mock_create_job.return_value = "job-123"
        mock_run.return_value = {"merges_performed": 5, "entity_types_processed": 2}

        # Import here to get the task with mocks active
        from app.entities.tasks import resolve_entities

        result = resolve_entities("person", matter_id="m-1")

        assert result == {"merges_performed": 5, "entity_types_processed": 2}
        mock_create_job.assert_called_once_with(
            mock_engine.return_value,
            "m-1",
            "entity_resolution",
            "Entity resolution: person",
        )
        # Should update to loading_entities (processing) then complete
        assert mock_update.call_count == 2
        calls = mock_update.call_args_list
        assert calls[0].args[2] == "loading_entities"  # stage
        assert calls[0].args[3] == "processing"  # status
        assert calls[1].args[2] == "complete"
        assert calls[1].args[3] == "complete"

    @patch("app.entities.tasks._get_sync_engine")
    @patch("app.entities.tasks._run_resolution")
    @patch("app.entities.tasks._create_job_sync")
    @patch("app.entities.tasks._update_stage")
    def test_marks_failed_on_error(self, mock_update, mock_create_job, mock_run, mock_engine):
        mock_engine.return_value = MagicMock()
        mock_create_job.return_value = "job-456"
        mock_run.side_effect = RuntimeError("Neo4j down")

        from app.entities.tasks import resolve_entities

        with pytest.raises(RuntimeError, match="Neo4j down"):
            resolve_entities(matter_id="m-2")

        # Should have called _update_stage with failed
        failed_calls = [c for c in mock_update.call_args_list if c.args[3] == "failed"]
        assert len(failed_calls) == 1
        assert failed_calls[0].kwargs.get("error") == "Neo4j down"

    @patch("app.entities.tasks._get_sync_engine")
    @patch("app.entities.tasks._create_job_sync")
    @patch("app.entities.tasks._update_stage")
    def test_label_defaults_to_all(self, mock_update, mock_create_job, mock_engine):
        """When no entity_type is provided, label should say 'all'."""
        mock_engine.return_value = MagicMock()
        mock_create_job.return_value = "job-789"

        with patch(
            "app.entities.tasks._run_resolution", return_value={"merges_performed": 0, "entity_types_processed": 0}
        ):
            from app.entities.tasks import resolve_entities

            resolve_entities()

        mock_create_job.assert_called_once()
        label = mock_create_job.call_args.args[3]
        assert "all" in label


class TestEntityResolutionAgentJobTracking:
    """Verify entity_resolution_agent creates and updates a job record."""

    @patch("app.entities.tasks._get_sync_engine")
    @patch("app.entities.tasks._create_job_sync")
    @patch("app.entities.tasks._update_stage")
    def test_creates_job_and_completes(self, mock_update, mock_create_job, mock_engine):
        mock_engine.return_value = MagicMock()
        mock_create_job.return_value = "job-agent-1"

        with patch("app.entities.resolution_agent.run_resolution_agent") as mock_agent:
            mock_agent.return_value = {"merges": 3}

            from app.entities.tasks import entity_resolution_agent

            result = entity_resolution_agent("m-1")

        assert result == {"merges": 3}
        mock_create_job.assert_called_once_with(
            mock_engine.return_value,
            "m-1",
            "entity_resolution",
            "Entity resolution agent",
        )
        # Should update stages through to complete
        complete_calls = [c for c in mock_update.call_args_list if c.args[2] == "complete"]
        assert len(complete_calls) == 1


class TestReprocessNeo4jJobTracking:
    """Verify reprocess_entities_to_neo4j creates and updates a job record."""

    @patch("app.entities.tasks._get_sync_engine")
    @patch("app.entities.tasks._create_job_sync")
    @patch("app.entities.tasks._update_stage")
    def test_creates_job_with_doc_count_label(self, mock_update, mock_create_job, mock_engine):
        mock_engine.return_value = MagicMock()
        mock_create_job.return_value = "job-neo4j-1"

        doc_ids = ["doc-1", "doc-2", "doc-3"]

        # Mock the async inner function by patching the external deps
        with (
            patch("app.config.Settings"),
            patch("neo4j.AsyncGraphDatabase") as mock_neo4j,
            patch("qdrant_client.QdrantClient") as mock_qdrant_cls,
        ):
            mock_driver = MagicMock()
            mock_driver.close = AsyncMock()
            mock_neo4j.driver.return_value = mock_driver

            mock_qdrant = MagicMock()
            mock_qdrant_cls.return_value = mock_qdrant
            mock_qdrant.scroll.return_value = ([], None)
            mock_qdrant.close = MagicMock()

            from app.entities.tasks import reprocess_entities_to_neo4j

            result = reprocess_entities_to_neo4j(doc_ids)

        mock_create_job.assert_called_once()
        label = mock_create_job.call_args.args[3]
        assert "3 docs" in label
        assert result["total"] == 3
