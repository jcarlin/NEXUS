"""Tests for ZIP extraction in the ingestion pipeline."""

from __future__ import annotations

import io
import zipfile
from unittest.mock import MagicMock, patch

from app.ingestion.tasks import _ZIP_SKIP_PATTERNS, process_zip


def _make_zip(files: dict[str, bytes]) -> bytes:
    """Create an in-memory ZIP file from a dict of {name: content}."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


def _make_mock_settings():
    s = MagicMock()
    s.minio_use_ssl = False
    s.minio_endpoint = "localhost:9000"
    s.minio_access_key = "test"
    s.minio_secret_key = "test"
    s.minio_bucket = "test"
    s.postgres_url_sync = "postgresql://test:test@localhost/test"
    return s


def test_zip_skip_patterns():
    """Known skip patterns should include __MACOSX and .DS_Store."""
    assert "__MACOSX" in _ZIP_SKIP_PATTERNS
    assert ".DS_Store" in _ZIP_SKIP_PATTERNS


def test_zip_creates_child_jobs():
    """process_zip should create a child job per valid file in the archive."""
    zip_bytes = _make_zip(
        {
            "doc1.pdf": b"fake pdf content",
            "doc2.txt": b"some text",
        }
    )
    mock_settings = _make_mock_settings()

    with (
        patch("app.ingestion.tasks._get_sync_engine", return_value=MagicMock()),
        patch("app.ingestion.tasks._download_from_minio", return_value=zip_bytes),
        patch("app.ingestion.tasks._upload_to_minio"),
        patch("app.ingestion.tasks._update_stage"),
        patch("app.ingestion.tasks._create_child_job", return_value="child-123") as mock_child,
        patch("app.ingestion.tasks.process_document") as mock_pd,
        patch("app.config.Settings", return_value=mock_settings),
    ):
        mock_pd.delay = MagicMock()
        result = process_zip.__wrapped__("job-123", "raw/job-123/archive.zip")

    assert result["status"] == "complete"
    assert len(result["child_jobs"]) == 2
    assert mock_child.call_count == 2
    assert mock_pd.delay.call_count == 2


def test_zip_skips_macosx():
    """Files under __MACOSX/ directory should be skipped."""
    zip_bytes = _make_zip(
        {
            "__MACOSX/._doc.pdf": b"mac resource fork",
            "doc.pdf": b"real content",
        }
    )
    mock_settings = _make_mock_settings()

    with (
        patch("app.ingestion.tasks._get_sync_engine", return_value=MagicMock()),
        patch("app.ingestion.tasks._download_from_minio", return_value=zip_bytes),
        patch("app.ingestion.tasks._upload_to_minio"),
        patch("app.ingestion.tasks._update_stage"),
        patch("app.ingestion.tasks._create_child_job", return_value="child-1") as mock_child,
        patch("app.ingestion.tasks.process_document") as mock_pd,
        patch("app.config.Settings", return_value=mock_settings),
    ):
        mock_pd.delay = MagicMock()
        process_zip.__wrapped__("job-1", "raw/job-1/test.zip")

    # Only the real doc.pdf should produce a child job
    assert mock_child.call_count == 1


def test_zip_skips_ds_store():
    """.DS_Store files should be skipped."""
    zip_bytes = _make_zip(
        {
            ".DS_Store": b"binary junk",
            "readme.txt": b"hello",
        }
    )
    mock_settings = _make_mock_settings()

    with (
        patch("app.ingestion.tasks._get_sync_engine", return_value=MagicMock()),
        patch("app.ingestion.tasks._download_from_minio", return_value=zip_bytes),
        patch("app.ingestion.tasks._upload_to_minio"),
        patch("app.ingestion.tasks._update_stage"),
        patch("app.ingestion.tasks._create_child_job", return_value="child-1") as mock_child,
        patch("app.ingestion.tasks.process_document") as mock_pd,
        patch("app.config.Settings", return_value=mock_settings),
    ):
        mock_pd.delay = MagicMock()
        process_zip.__wrapped__("job-1", "raw/job-1/test.zip")

    assert mock_child.call_count == 1


def test_zip_skips_nested_zip():
    """Nested .zip files inside an archive should be skipped."""
    zip_bytes = _make_zip(
        {
            "inner.zip": b"nested zip content",
            "real.txt": b"hello",
        }
    )
    mock_settings = _make_mock_settings()

    with (
        patch("app.ingestion.tasks._get_sync_engine", return_value=MagicMock()),
        patch("app.ingestion.tasks._download_from_minio", return_value=zip_bytes),
        patch("app.ingestion.tasks._upload_to_minio"),
        patch("app.ingestion.tasks._update_stage"),
        patch("app.ingestion.tasks._create_child_job", return_value="child-1") as mock_child,
        patch("app.ingestion.tasks.process_document") as mock_pd,
        patch("app.config.Settings", return_value=mock_settings),
    ):
        mock_pd.delay = MagicMock()
        process_zip.__wrapped__("job-1", "raw/job-1/test.zip")

    # Only real.txt should produce a child job
    assert mock_child.call_count == 1


def test_zip_empty_archive():
    """An empty ZIP should complete with 0 child jobs."""
    zip_bytes = _make_zip({})
    mock_settings = _make_mock_settings()

    with (
        patch("app.ingestion.tasks._get_sync_engine", return_value=MagicMock()),
        patch("app.ingestion.tasks._download_from_minio", return_value=zip_bytes),
        patch("app.ingestion.tasks._upload_to_minio"),
        patch("app.ingestion.tasks._update_stage"),
        patch("app.ingestion.tasks._create_child_job") as mock_child,
        patch("app.ingestion.tasks.process_document") as mock_pd,
        patch("app.config.Settings", return_value=mock_settings),
    ):
        mock_pd.delay = MagicMock()
        result = process_zip.__wrapped__("job-1", "raw/job-1/empty.zip")

    assert result["child_jobs"] == []
    assert mock_child.call_count == 0
