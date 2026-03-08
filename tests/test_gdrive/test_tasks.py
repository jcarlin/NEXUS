"""Unit tests for Google Drive Celery tasks."""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4


class TestSyncGDriveFolder:
    @patch("app.gdrive.tasks._get_sync_engine")
    @patch("app.gdrive.tasks._get_settings")
    @patch("app.gdrive.tasks._update_stage")
    @patch("app.gdrive.tasks._get_connection_tokens_sync")
    @patch("app.gdrive.tasks._get_sync_map")
    @patch("app.gdrive.tasks._get_file_metadata")
    @patch("app.gdrive.tasks._upsert_sync_state")
    @patch("app.common.storage.StorageClient")
    @patch("app.ingestion.tasks.process_document")
    def test_sync_skips_unchanged_files(
        self,
        mock_process,
        mock_storage_cls,
        mock_upsert,
        mock_meta,
        mock_sync_map,
        mock_tokens,
        mock_stage,
        mock_settings,
        mock_engine,
    ):
        """Files with matching modified_time should be skipped."""
        from app.gdrive.tasks import sync_gdrive_folder

        engine = MagicMock()
        mock_engine.return_value = engine

        settings = MagicMock()
        settings.gdrive_encryption_key = "test-key"
        mock_settings.return_value = settings

        mock_tokens.return_value = '{"token":"t","refresh_token":"r"}'

        # File already synced with same modified_time
        mock_sync_map.return_value = {
            "file1": {"drive_modified_time": "2026-01-01T00:00:00Z", "content_hash": "abc", "sync_status": "synced"},
        }

        mock_meta.return_value = {
            "id": "file1",
            "name": "doc.pdf",
            "mimeType": "application/pdf",
            "modifiedTime": "2026-01-01T00:00:00Z",  # Same as synced
        }

        result = sync_gdrive_folder(
            job_id=str(uuid4()),
            connection_id=str(uuid4()),
            matter_id=str(uuid4()),
            file_ids=["file1"],
        )

        assert result["skipped"] == 1
        assert result["processed"] == 0
        mock_upsert.assert_not_called()

    @patch("app.gdrive.tasks._get_sync_engine")
    @patch("app.gdrive.tasks._get_settings")
    @patch("app.gdrive.tasks._update_stage")
    @patch("app.gdrive.tasks._get_connection_tokens_sync")
    @patch("app.gdrive.tasks._get_sync_map")
    @patch("app.gdrive.tasks._get_file_metadata")
    @patch("app.gdrive.tasks._upsert_sync_state")
    @patch("app.common.storage.StorageClient")
    @patch("app.ingestion.tasks.process_document")
    @patch("app.gdrive.service.GDriveService")
    def test_sync_processes_new_files(
        self,
        mock_service_cls,
        mock_process,
        mock_storage_cls,
        mock_upsert,
        mock_meta,
        mock_sync_map,
        mock_tokens,
        mock_stage,
        mock_settings,
        mock_engine,
    ):
        """New files should be downloaded, uploaded to MinIO, and dispatched."""
        from app.gdrive.tasks import sync_gdrive_folder

        engine = MagicMock()
        mock_engine.return_value = engine

        settings = MagicMock()
        settings.gdrive_encryption_key = "test-key"
        mock_settings.return_value = settings

        mock_tokens.return_value = '{"token":"t","refresh_token":"r"}'
        mock_sync_map.return_value = {}  # No existing sync

        mock_meta.return_value = {
            "id": "file1",
            "name": "report.pdf",
            "mimeType": "application/pdf",
            "modifiedTime": "2026-01-01T00:00:00Z",
        }

        mock_service = MagicMock()
        mock_service.download_file.return_value = (b"fake-pdf-content", "")
        mock_service_cls.return_value = mock_service
        mock_process.delay = MagicMock()

        result = sync_gdrive_folder(
            job_id=str(uuid4()),
            connection_id=str(uuid4()),
            matter_id=str(uuid4()),
            file_ids=["file1"],
        )

        assert result["processed"] == 1
        assert result["skipped"] == 0
        mock_process.delay.assert_called_once()
        mock_upsert.assert_called_once()

    @patch("app.gdrive.tasks._get_sync_engine")
    @patch("app.gdrive.tasks._get_settings")
    @patch("app.gdrive.tasks._update_stage")
    @patch("app.gdrive.tasks._get_connection_tokens_sync")
    @patch("app.gdrive.tasks._get_sync_map")
    @patch("app.gdrive.tasks._get_file_metadata")
    @patch("app.common.storage.StorageClient")
    def test_sync_handles_missing_files(
        self,
        mock_storage_cls,
        mock_meta,
        mock_sync_map,
        mock_tokens,
        mock_stage,
        mock_settings,
        mock_engine,
    ):
        """Files not found on Drive should be counted as errors."""
        from app.gdrive.tasks import sync_gdrive_folder

        mock_engine.return_value = MagicMock()
        mock_settings.return_value = MagicMock(gdrive_encryption_key="k")
        mock_tokens.return_value = '{"token":"t"}'
        mock_sync_map.return_value = {}
        mock_meta.return_value = None  # File not found

        result = sync_gdrive_folder(
            job_id=str(uuid4()),
            connection_id=str(uuid4()),
            matter_id=str(uuid4()),
            file_ids=["missing-file"],
        )

        assert result["errors"] == 1
        assert result["processed"] == 0

    @patch("app.gdrive.tasks._get_sync_engine")
    @patch("app.gdrive.tasks._get_settings")
    @patch("app.gdrive.tasks._update_stage")
    @patch("app.gdrive.tasks._get_connection_tokens_sync")
    @patch("app.gdrive.tasks._get_sync_map")
    @patch("app.gdrive.tasks._get_file_metadata")
    @patch("app.gdrive.tasks._upsert_sync_state")
    @patch("app.common.storage.StorageClient")
    @patch("app.ingestion.tasks.process_document")
    @patch("app.gdrive.service.GDriveService")
    def test_sync_exports_google_docs_as_pdf(
        self,
        mock_service_cls,
        mock_process,
        mock_storage_cls,
        mock_upsert,
        mock_meta,
        mock_sync_map,
        mock_tokens,
        mock_stage,
        mock_settings,
        mock_engine,
    ):
        """Google Docs should get .pdf suffix appended."""
        from app.gdrive.tasks import sync_gdrive_folder

        engine = MagicMock()
        mock_engine.return_value = engine
        mock_settings.return_value = MagicMock(gdrive_encryption_key="k")
        mock_tokens.return_value = '{"token":"t"}'
        mock_sync_map.return_value = {}

        mock_meta.return_value = {
            "id": "gdoc1",
            "name": "My Document",
            "mimeType": "application/vnd.google-apps.document",
            "modifiedTime": "2026-01-01T00:00:00Z",
        }

        mock_service = MagicMock()
        mock_service.download_file.return_value = (b"exported-pdf", ".pdf")
        mock_service_cls.return_value = mock_service
        mock_process.delay = MagicMock()

        result = sync_gdrive_folder(
            job_id=str(uuid4()),
            connection_id=str(uuid4()),
            matter_id=str(uuid4()),
            file_ids=["gdoc1"],
        )

        assert result["processed"] == 1
        mock_upsert.assert_called_once()
