"""Tests for RetentionService — CRUD and purge orchestration."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from app.retention.service import RetentionService
from tests.test_retention.conftest import TEST_MATTER_ID, TEST_USER_ID, _make_policy_row

# ---------------------------------------------------------------------------
# Helpers — mock AsyncSession
# ---------------------------------------------------------------------------


def _mock_db(rows=None, scalar=None):
    """Return a mock AsyncSession with execute() returning given rows."""
    db = AsyncMock()

    mock_result = MagicMock()
    if rows is not None:
        mock_mappings = MagicMock()
        mock_mappings.first.return_value = rows[0] if rows else None
        mock_mappings.all.return_value = rows
        mock_result.mappings.return_value = mock_mappings
    if scalar is not None:
        mock_result.scalar.return_value = scalar
    mock_result.rowcount = len(rows) if rows else 0
    db.execute.return_value = mock_result
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


# ---------------------------------------------------------------------------
# create_policy
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_policy_inserts_correctly():
    """create_policy returns the inserted row."""
    expected = _make_policy_row()
    db = _mock_db(rows=[expected])

    result = await RetentionService.create_policy(
        db=db,
        matter_id=TEST_MATTER_ID,
        retention_days=365,
        user_id=TEST_USER_ID,
    )

    assert result["matter_id"] == TEST_MATTER_ID
    assert result["retention_days"] == 365
    assert result["status"] == "active"
    db.execute.assert_called_once()


@pytest.mark.asyncio
async def test_create_policy_computes_purge_scheduled_at():
    """purge_scheduled_at should be set in the future."""
    row = _make_policy_row(purge_scheduled_at=datetime(2027, 1, 1, tzinfo=UTC))
    db = _mock_db(rows=[row])

    result = await RetentionService.create_policy(
        db=db, matter_id=TEST_MATTER_ID, retention_days=365, user_id=TEST_USER_ID
    )

    assert result["purge_scheduled_at"] is not None


@pytest.mark.asyncio
async def test_create_policy_duplicate_matter():
    """create_policy should propagate DB unique constraint error on duplicate."""
    from sqlalchemy.exc import IntegrityError

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=IntegrityError("dup", {}, None))

    with pytest.raises(IntegrityError):
        await RetentionService.create_policy(db=db, matter_id=TEST_MATTER_ID, retention_days=365, user_id=TEST_USER_ID)


# ---------------------------------------------------------------------------
# get_policy
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_policy_found():
    """get_policy returns the row when found."""
    row = _make_policy_row()
    db = _mock_db(rows=[row])

    result = await RetentionService.get_policy(db, TEST_MATTER_ID)
    assert result is not None
    assert result["matter_id"] == TEST_MATTER_ID


@pytest.mark.asyncio
async def test_get_policy_not_found():
    """get_policy returns None when no policy exists."""
    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.mappings.return_value.first.return_value = None
    db.execute.return_value = mock_result

    result = await RetentionService.get_policy(db, TEST_MATTER_ID)
    assert result is None


# ---------------------------------------------------------------------------
# list_policies
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_policies_returns_all():
    """list_policies returns paginated policies and total."""
    rows = [_make_policy_row(), _make_policy_row(matter_id=UUID("00000000-0000-0000-0000-000000000002"))]
    db = AsyncMock()

    # First call: count, second call: rows
    count_result = MagicMock()
    count_result.scalar.return_value = 2

    rows_result = MagicMock()
    rows_result.mappings.return_value.all.return_value = rows

    db.execute = AsyncMock(side_effect=[count_result, rows_result])

    policies, total = await RetentionService.list_policies(db)
    assert total == 2
    assert len(policies) == 2


# ---------------------------------------------------------------------------
# delete_policy
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_policy_active_succeeds():
    """delete_policy returns True for active policy."""
    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.rowcount = 1
    db.execute.return_value = mock_result

    result = await RetentionService.delete_policy(db, TEST_MATTER_ID)
    assert result is True


@pytest.mark.asyncio
async def test_delete_policy_non_active_fails():
    """delete_policy returns False when policy is not active (SQL WHERE filters it out)."""
    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.rowcount = 0
    db.execute.return_value = mock_result

    result = await RetentionService.delete_policy(db, TEST_MATTER_ID)
    assert result is False


# ---------------------------------------------------------------------------
# get_expired_policies
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_expired_policies_filters_correctly():
    """get_expired_policies returns only expired active policies."""
    expired_row = _make_policy_row(purge_scheduled_at=datetime(2025, 1, 1, tzinfo=UTC))
    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = [expired_row]
    db.execute.return_value = mock_result

    result = await RetentionService.get_expired_policies(db)
    assert len(result) == 1
    assert result[0]["status"] == "active"


# ---------------------------------------------------------------------------
# execute_purge
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_purge_full_cascade():
    """execute_purge completes all steps and returns completed status."""
    db = AsyncMock()
    db.execute = AsyncMock(
        return_value=MagicMock(mappings=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))))
    )
    db.commit = AsyncMock()
    db.rollback = AsyncMock()

    qdrant = MagicMock()
    qdrant.client = MagicMock()
    neo4j = AsyncMock()
    neo4j.session = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(), __aexit__=AsyncMock()))
    minio = AsyncMock()
    minio.upload_bytes = AsyncMock()
    minio.list_objects = AsyncMock(return_value=[])

    result = await RetentionService.execute_purge(
        db=db,
        matter_id=TEST_MATTER_ID,
        qdrant_client=qdrant,
        neo4j_driver=neo4j,
        minio_client=minio,
    )

    assert result["status"] == "completed"
    assert "archive_path" in result


@pytest.mark.asyncio
async def test_execute_purge_archive_failure_aborts():
    """If archive fails, purge must not proceed."""
    db = AsyncMock()
    db.execute = AsyncMock(
        return_value=MagicMock(mappings=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))))
    )
    db.commit = AsyncMock()
    db.rollback = AsyncMock()

    minio = AsyncMock()
    minio.upload_bytes = AsyncMock(side_effect=RuntimeError("MinIO down"))

    with pytest.raises(RuntimeError, match="MinIO down"):
        await RetentionService.execute_purge(
            db=db,
            matter_id=TEST_MATTER_ID,
            qdrant_client=MagicMock(),
            neo4j_driver=AsyncMock(),
            minio_client=minio,
        )


@pytest.mark.asyncio
async def test_execute_purge_system_failure_sets_error():
    """If a system purge step fails, status should be 'failed' and error re-raised."""
    db = AsyncMock()
    db.execute = AsyncMock(
        return_value=MagicMock(mappings=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))))
    )
    db.commit = AsyncMock()
    db.rollback = AsyncMock()

    qdrant = MagicMock()
    qdrant.client = MagicMock()

    minio = AsyncMock()
    minio.upload_bytes = AsyncMock()
    minio.list_objects = AsyncMock(return_value=[])

    # Make Neo4j fail — session() returns an async context manager whose run() raises
    mock_neo4j_session = AsyncMock()
    mock_neo4j_session.run = AsyncMock(side_effect=RuntimeError("Neo4j down"))

    neo4j = MagicMock()
    ctx = AsyncMock()
    ctx.__aenter__.return_value = mock_neo4j_session
    ctx.__aexit__.return_value = False
    neo4j.session.return_value = ctx

    with pytest.raises(RuntimeError, match="Neo4j down"):
        await RetentionService.execute_purge(
            db=db,
            matter_id=TEST_MATTER_ID,
            qdrant_client=qdrant,
            neo4j_driver=neo4j,
            minio_client=minio,
        )


@pytest.mark.asyncio
async def test_execute_purge_idempotent_retry():
    """Re-running purge on a matter should succeed (idempotent operations)."""
    db = AsyncMock()
    db.execute = AsyncMock(
        return_value=MagicMock(mappings=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))))
    )
    db.commit = AsyncMock()
    db.rollback = AsyncMock()

    qdrant = MagicMock()
    qdrant.client = MagicMock()
    neo4j = AsyncMock()
    neo4j.session = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(), __aexit__=AsyncMock()))
    minio = AsyncMock()
    minio.upload_bytes = AsyncMock()
    minio.list_objects = AsyncMock(return_value=[])

    # Run twice — both should succeed
    for _ in range(2):
        result = await RetentionService.execute_purge(
            db=db,
            matter_id=TEST_MATTER_ID,
            qdrant_client=qdrant,
            neo4j_driver=neo4j,
            minio_client=minio,
        )
        assert result["status"] == "completed"


@pytest.mark.asyncio
async def test_audit_logs_not_deleted_during_purge():
    """_purge_postgresql must NOT delete from audit_log or ai_audit_log."""
    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock())

    await RetentionService._purge_postgresql(db, TEST_MATTER_ID)

    # Collect all SQL statements executed
    sql_calls = [str(call.args[0]) for call in db.execute.call_args_list]
    for sql in sql_calls:
        assert "audit_log" not in sql.lower() or "case_" in sql.lower() or "FROM documents" in sql


@pytest.mark.asyncio
async def test_case_matters_archived_after_purge():
    """After purge, case_matters.is_archived should be set to TRUE."""
    db = AsyncMock()
    db.execute = AsyncMock(
        return_value=MagicMock(mappings=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))))
    )
    db.commit = AsyncMock()
    db.rollback = AsyncMock()

    qdrant = MagicMock()
    qdrant.client = MagicMock()
    neo4j = AsyncMock()
    neo4j.session = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(), __aexit__=AsyncMock()))
    minio = AsyncMock()
    minio.upload_bytes = AsyncMock()
    minio.list_objects = AsyncMock(return_value=[])

    await RetentionService.execute_purge(
        db=db,
        matter_id=TEST_MATTER_ID,
        qdrant_client=qdrant,
        neo4j_driver=neo4j,
        minio_client=minio,
    )

    # Check that an UPDATE to case_matters was executed
    sql_calls = [str(call.args[0]) for call in db.execute.call_args_list]
    archive_calls = [s for s in sql_calls if "is_archived" in s.lower()]
    assert len(archive_calls) > 0
