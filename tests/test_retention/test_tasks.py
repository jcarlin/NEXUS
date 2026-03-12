"""Tests for retention Celery tasks."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tests.test_retention.conftest import TEST_MATTER_ID

# ---------------------------------------------------------------------------
# execute_scheduled_purge
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_scheduled_purge_calls_service():
    """execute_scheduled_purge calls RetentionService.execute_purge."""
    with (
        patch("app.retention.tasks.asyncio.run") as mock_run,
    ):
        mock_run.return_value = {"status": "completed", "archive_path": "archives/test.zip"}

        from app.retention.tasks import execute_scheduled_purge

        result = execute_scheduled_purge(str(TEST_MATTER_ID))

    assert result["status"] == "completed"
    mock_run.assert_called_once()


@pytest.mark.asyncio
async def test_execute_scheduled_purge_handles_errors():
    """execute_scheduled_purge re-raises on failure."""
    with patch("app.retention.tasks.asyncio.run", side_effect=RuntimeError("purge failed")):
        from app.retention.tasks import execute_scheduled_purge

        with pytest.raises(RuntimeError, match="purge failed"):
            execute_scheduled_purge(str(TEST_MATTER_ID))


# ---------------------------------------------------------------------------
# check_retention_expirations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_expirations_finds_expired():
    """check_retention_expirations finds expired policies."""
    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_result = MagicMock()
    mock_result.fetchall.return_value = [(str(TEST_MATTER_ID),)]
    mock_conn.execute.return_value = mock_result
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_engine.connect.return_value = mock_conn
    mock_engine.dispose = MagicMock()

    with (
        patch("app.retention.tasks._get_sync_engine", return_value=mock_engine),
        patch("app.retention.tasks.execute_scheduled_purge") as mock_purge_task,
    ):
        mock_purge_task.delay = MagicMock()

        from app.retention.tasks import check_retention_expirations

        result = check_retention_expirations()

    assert result["expired_count"] == 1
    assert str(TEST_MATTER_ID) in result["scheduled_matter_ids"]
    mock_purge_task.delay.assert_called_once_with(str(TEST_MATTER_ID))


@pytest.mark.asyncio
async def test_check_expirations_skips_non_expired():
    """check_retention_expirations returns 0 when nothing is expired."""
    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_result = MagicMock()
    mock_result.fetchall.return_value = []
    mock_conn.execute.return_value = mock_result
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_engine.connect.return_value = mock_conn
    mock_engine.dispose = MagicMock()

    with patch("app.retention.tasks._get_sync_engine", return_value=mock_engine):
        from app.retention.tasks import check_retention_expirations

        result = check_retention_expirations()

    assert result["expired_count"] == 0
    assert result["scheduled_matter_ids"] == []


@pytest.mark.asyncio
async def test_check_expirations_schedules_tasks():
    """check_retention_expirations calls delay() for each expired matter."""
    mid1 = "00000000-0000-0000-0000-000000000001"
    mid2 = "00000000-0000-0000-0000-000000000002"

    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_result = MagicMock()
    mock_result.fetchall.return_value = [(mid1,), (mid2,)]
    mock_conn.execute.return_value = mock_result
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_engine.connect.return_value = mock_conn
    mock_engine.dispose = MagicMock()

    with (
        patch("app.retention.tasks._get_sync_engine", return_value=mock_engine),
        patch("app.retention.tasks.execute_scheduled_purge") as mock_purge_task,
    ):
        mock_purge_task.delay = MagicMock()

        from app.retention.tasks import check_retention_expirations

        result = check_retention_expirations()

    assert result["expired_count"] == 2
    assert mock_purge_task.delay.call_count == 2


def test_task_is_registered():
    """execute_scheduled_purge should be a registered Celery task."""
    from app.retention.tasks import execute_scheduled_purge

    assert hasattr(execute_scheduled_purge, "delay")
    assert execute_scheduled_purge.name == "app.retention.tasks.execute_scheduled_purge"


def test_beat_schedule_includes_expiration_check():
    """Celery beat schedule should include the retention expiration check."""
    from workers.celery_app import celery_app

    schedule = celery_app.conf.beat_schedule
    assert "check-retention-expirations" in schedule
    entry = schedule["check-retention-expirations"]
    assert entry["task"] == "app.retention.tasks.check_retention_expirations"
    assert entry["schedule"] == 86400


@pytest.mark.asyncio
async def test_idempotent_re_execution():
    """Running execute_scheduled_purge twice should succeed both times."""
    with patch("app.retention.tasks.asyncio.run") as mock_run:
        mock_run.return_value = {"status": "completed", "archive_path": "archives/test.zip"}

        from app.retention.tasks import execute_scheduled_purge

        result1 = execute_scheduled_purge(str(TEST_MATTER_ID))
        result2 = execute_scheduled_purge(str(TEST_MATTER_ID))

    assert result1["status"] == "completed"
    assert result2["status"] == "completed"
    assert mock_run.call_count == 2
