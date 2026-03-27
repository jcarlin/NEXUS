"""Tests for external task tracking service."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.scripts.service import ExternalTaskService


@pytest.mark.asyncio
async def test_register_creates_task():
    """Register creates a new external task row."""
    task_id = uuid4()
    mock_row = MagicMock()
    mock_row._mapping = {
        "id": task_id,
        "name": "NER Pass",
        "script_name": "run_ner_pass.py",
        "status": "running",
        "total": 500,
        "processed": 0,
        "failed": 0,
        "error": None,
        "metadata_": {},
        "matter_id": None,
        "started_at": "2026-03-27T00:00:00Z",
        "updated_at": "2026-03-27T00:00:00Z",
        "completed_at": None,
    }
    mock_result = MagicMock()
    mock_result.one.return_value = mock_row

    mock_db = AsyncMock()
    mock_db.execute.return_value = mock_result

    result = await ExternalTaskService.register(
        db=mock_db,
        name="NER Pass",
        script_name="run_ner_pass.py",
        total=500,
    )

    assert result["name"] == "NER Pass"
    assert result["total"] == 500
    mock_db.execute.assert_called_once()


@pytest.mark.asyncio
async def test_update_sets_fields():
    """Update patches specified fields on the task."""
    task_id = uuid4()
    mock_row = MagicMock()
    mock_row._mapping = {
        "id": task_id,
        "name": "NER Pass",
        "script_name": "run_ner_pass.py",
        "status": "running",
        "total": 500,
        "processed": 100,
        "failed": 2,
        "error": None,
        "metadata_": {},
        "matter_id": None,
        "started_at": "2026-03-27T00:00:00Z",
        "updated_at": "2026-03-27T00:00:00Z",
        "completed_at": None,
    }
    mock_result = MagicMock()
    mock_result.one_or_none.return_value = mock_row

    mock_db = AsyncMock()
    mock_db.execute.return_value = mock_result

    result = await ExternalTaskService.update(db=mock_db, task_id=task_id, processed=100, failed=2)

    assert result is not None
    assert result["processed"] == 100
    assert result["failed"] == 2


@pytest.mark.asyncio
async def test_update_not_found_returns_none():
    """Update returns None if task doesn't exist."""
    mock_result = MagicMock()
    mock_result.one_or_none.return_value = None

    mock_db = AsyncMock()
    mock_db.execute.return_value = mock_result

    result = await ExternalTaskService.update(db=mock_db, task_id=uuid4(), processed=50)
    assert result is None


@pytest.mark.asyncio
async def test_list_tasks_pagination():
    """List tasks returns paginated results."""
    mock_db = AsyncMock()

    count_result = MagicMock()
    count_result.scalar_one.return_value = 2

    row1 = MagicMock()
    row1._mapping = {"id": uuid4(), "name": "Task 1", "status": "running"}
    row2 = MagicMock()
    row2._mapping = {"id": uuid4(), "name": "Task 2", "status": "complete"}
    items_result = MagicMock()
    items_result.all.return_value = [row1, row2]

    mock_db.execute.side_effect = [count_result, items_result]

    items, total = await ExternalTaskService.list_tasks(db=mock_db)
    assert total == 2
    assert len(items) == 2


@pytest.mark.asyncio
async def test_expire_stale_marks_old_tasks():
    """Expire stale marks running tasks with old updated_at as stale."""
    mock_result = MagicMock()
    mock_result.rowcount = 3

    mock_db = AsyncMock()
    mock_db.execute.return_value = mock_result

    count = await ExternalTaskService.expire_stale(db=mock_db, stale_minutes=30)
    assert count == 3
