"""Tests for the dataset service layer.

Each test creates a mock AsyncSession and exercises DatasetService static
methods without touching a real database.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from sqlalchemy.exc import IntegrityError

from app.datasets.service import MAX_TREE_DEPTH, DatasetService

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MATTER_ID = UUID("00000000-0000-0000-0000-000000000001")
_DATASET_ID = UUID("00000000-0000-0000-0000-000000000010")
_USER_ID = UUID("00000000-0000-0000-0000-000000000099")
_DOC_ID_1 = UUID("00000000-0000-0000-0000-000000000030")
_DOC_ID_2 = UUID("00000000-0000-0000-0000-000000000031")
_NOW = datetime(2025, 1, 1, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_session() -> AsyncMock:
    """Return a mock AsyncSession with a configurable execute method."""
    session = AsyncMock()
    return session


def _mock_result(rows=None, scalar=None, row_count=0):
    """Create a mock result object returned by session.execute().

    Supports .mappings().one(), .mappings().first(), .mappings().all(),
    .scalar_one(), .scalar_one_or_none(), .first(), .all(), and .rowcount.
    """
    result = MagicMock()
    result.rowcount = row_count

    mappings = MagicMock()
    if rows and len(rows) == 1:
        mappings.one.return_value = rows[0]
        mappings.first.return_value = rows[0]
    elif rows:
        mappings.first.return_value = rows[0]
    else:
        mappings.one.side_effect = Exception("No row found")
        mappings.first.return_value = None
    mappings.all.return_value = rows or []
    result.mappings.return_value = mappings

    result.scalar_one.return_value = scalar
    result.scalar_one_or_none.return_value = scalar

    if rows:
        result.first.return_value = rows[0]
        result.all.return_value = rows
    else:
        result.first.return_value = None
        result.all.return_value = []

    return result


# ---------------------------------------------------------------------------
# create_dataset — depth limit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_dataset_depth_limit() -> None:
    """Creating a dataset should raise ValueError when tree depth exceeds MAX_TREE_DEPTH."""
    session = _mock_session()
    parent_id = UUID("00000000-0000-0000-0000-000000000020")

    # _get_depth returns MAX_TREE_DEPTH (i.e., already at limit)
    depth_result = _mock_result(scalar=MAX_TREE_DEPTH)
    session.execute.return_value = depth_result

    with pytest.raises(ValueError, match="Maximum folder depth"):
        await DatasetService.create_dataset(
            session,
            name="Too Deep",
            description="",
            parent_id=parent_id,
            matter_id=_MATTER_ID,
            created_by=_USER_ID,
        )


# ---------------------------------------------------------------------------
# create_dataset — unique name (IntegrityError)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_dataset_unique_name() -> None:
    """Creating a dataset with a duplicate name should propagate IntegrityError."""
    session = _mock_session()

    # No parent — skip depth check, go straight to INSERT
    # Simulate IntegrityError from duplicate name
    session.execute.side_effect = IntegrityError(
        "duplicate key",
        params=None,
        orig=Exception("unique_violation"),
    )

    with pytest.raises(IntegrityError):
        await DatasetService.create_dataset(
            session,
            name="Duplicate",
            description="",
            parent_id=None,
            matter_id=_MATTER_ID,
            created_by=_USER_ID,
        )


# ---------------------------------------------------------------------------
# get_dataset_tree — tree assembly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_dataset_tree() -> None:
    """get_dataset_tree should assemble flat CTE rows into a proper tree."""
    session = _mock_session()

    root_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    child_id = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")

    tree_rows = [
        {"id": root_id, "name": "Root", "description": "", "parent_id": None, "document_count": 5},
        {"id": child_id, "name": "Child", "description": "", "parent_id": root_id, "document_count": 3},
    ]

    tree_result = _mock_result(rows=tree_rows)
    session.execute.return_value = tree_result

    roots, total = await DatasetService.get_dataset_tree(session, _MATTER_ID)

    assert total == 2
    assert len(roots) == 1
    assert roots[0].name == "Root"
    assert roots[0].document_count == 5
    assert len(roots[0].children) == 1
    assert roots[0].children[0].name == "Child"
    assert roots[0].children[0].document_count == 3


# ---------------------------------------------------------------------------
# get_document_ids_for_dataset
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_document_ids_for_dataset() -> None:
    """get_document_ids_for_dataset should return job_ids as strings."""
    session = _mock_session()

    job_id_1 = "job-aaa"
    job_id_2 = "job-bbb"

    result = _mock_result()
    result.all.return_value = [(job_id_1,), (job_id_2,), (None,)]
    session.execute.return_value = result

    doc_ids = await DatasetService.get_document_ids_for_dataset(
        session,
        _DATASET_ID,
        _MATTER_ID,
    )

    assert doc_ids == [job_id_1, job_id_2]


# ---------------------------------------------------------------------------
# check_dataset_access — default open
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_access_default_open() -> None:
    """When no access rows exist, check_dataset_access should return True (default-open)."""
    session = _mock_session()

    # First execute: check for restrictions — no rows
    no_restrictions = _mock_result()
    no_restrictions.first.return_value = None
    session.execute.return_value = no_restrictions

    result = await DatasetService.check_dataset_access(
        session,
        _DATASET_ID,
        _USER_ID,
        _MATTER_ID,
    )

    assert result is True


# ---------------------------------------------------------------------------
# check_dataset_access — restricted, user listed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_access_restricted() -> None:
    """When access rows exist and user is listed, access should be granted."""
    session = _mock_session()

    # First call: restrictions exist; second call: user is listed
    has_restrictions = _mock_result(rows=[{"id": 1}])
    has_restrictions.first.return_value = (1,)  # not None
    user_listed = _mock_result(rows=[{"id": 1}])
    user_listed.first.return_value = (1,)

    session.execute.side_effect = [has_restrictions, user_listed]

    result = await DatasetService.check_dataset_access(
        session,
        _DATASET_ID,
        _USER_ID,
        _MATTER_ID,
    )

    assert result is True


# ---------------------------------------------------------------------------
# check_dataset_access — restricted, user NOT listed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_access_denied() -> None:
    """When access rows exist but user is not listed, access should be denied."""
    session = _mock_session()

    has_restrictions = _mock_result(rows=[{"id": 1}])
    has_restrictions.first.return_value = (1,)  # not None
    user_not_listed = _mock_result()
    user_not_listed.first.return_value = None

    session.execute.side_effect = [has_restrictions, user_not_listed]

    result = await DatasetService.check_dataset_access(
        session,
        _DATASET_ID,
        _USER_ID,
        _MATTER_ID,
    )

    assert result is False


# ---------------------------------------------------------------------------
# assign_documents — ON CONFLICT
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_assign_documents() -> None:
    """assign_documents should return count of new assignments via INSERT ON CONFLICT."""
    session = _mock_session()

    # First call: get_dataset (verify dataset exists) — returns a dataset row
    dataset_row = {
        "id": _DATASET_ID,
        "matter_id": _MATTER_ID,
        "name": "Test",
        "description": "",
        "parent_id": None,
        "created_by": _USER_ID,
        "created_at": _NOW,
        "updated_at": _NOW,
        "document_count": 0,
        "children_count": 0,
    }
    get_dataset_result = _mock_result(rows=[dataset_row])

    # Per-document INSERT results: first doc is new (rowcount=1), second is duplicate (rowcount=0)
    insert_result_1 = _mock_result(row_count=1)
    insert_result_2 = _mock_result(row_count=0)

    session.execute.side_effect = [get_dataset_result, insert_result_1, insert_result_2]

    count = await DatasetService.assign_documents(
        session,
        _DATASET_ID,
        [_DOC_ID_1, _DOC_ID_2],
        _MATTER_ID,
        _USER_ID,
    )

    assert count == 1
    # 3 calls total: 1 for get_dataset, 2 for inserts
    assert session.execute.call_count == 3
