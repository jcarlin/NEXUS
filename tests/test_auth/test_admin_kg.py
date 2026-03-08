"""Tests for Knowledge Graph admin endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient

from app.auth.schemas import UserRecord

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DOC_ID_1 = uuid4()
_DOC_ID_2 = uuid4()


def _fake_doc_rows() -> list[dict]:
    return [
        {
            "id": _DOC_ID_1,
            "filename": "contract.pdf",
            "entity_count": 5,
            "created_at": datetime(2025, 6, 1, tzinfo=UTC),
        },
        {
            "id": _DOC_ID_2,
            "filename": "memo.docx",
            "entity_count": 0,
            "created_at": datetime(2025, 6, 2, tzinfo=UTC),
        },
    ]


def _mock_db_session(rows: list[dict]) -> AsyncMock:
    """Build an AsyncMock session whose execute returns *rows* for every call."""
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = rows
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    return mock_session


# ---------------------------------------------------------------------------
# GET /admin/knowledge-graph/status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_kg_status_200(client: AsyncClient) -> None:
    """Admin can retrieve KG status with node/edge counts and documents."""
    mock_gs = AsyncMock()
    mock_gs.get_graph_stats = AsyncMock(
        return_value={
            "total_nodes": 100,
            "total_edges": 50,
            "node_counts": {"Entity": 80, "Document": 20},
            "edge_counts": {"MENTIONS": 50},
        }
    )
    mock_gs._run_query = AsyncMock(
        return_value=[
            {"did": str(_DOC_ID_1)},
        ]
    )

    rows = _fake_doc_rows()
    mock_session = _mock_db_session(rows)

    from app.dependencies import get_db

    async def mock_get_db():
        yield mock_session

    client._transport.app.dependency_overrides[get_db] = mock_get_db

    with patch("app.auth.admin_router.get_graph_service", return_value=mock_gs):
        try:
            response = await client.get("/api/v1/admin/knowledge-graph/status")
        finally:
            del client._transport.app.dependency_overrides[get_db]

    assert response.status_code == 200
    body = response.json()
    assert body["total_nodes"] == 100
    assert body["total_edges"] == 50
    assert body["node_counts"]["Entity"] == 80
    assert body["total_documents"] == 2
    assert body["indexed_documents"] == 1
    # First doc is indexed (its ID was returned from Neo4j)
    docs = body["documents"]
    doc_map = {d["doc_id"]: d for d in docs}
    assert doc_map[str(_DOC_ID_1)]["neo4j_indexed"] is True
    assert doc_map[str(_DOC_ID_2)]["neo4j_indexed"] is False


# ---------------------------------------------------------------------------
# POST /admin/knowledge-graph/reprocess
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_kg_reprocess_with_doc_ids(client: AsyncClient) -> None:
    """Reprocess dispatches a Celery task for given document IDs."""
    mock_task = MagicMock()
    mock_task.id = "celery-task-123"

    mock_session = _mock_db_session([])

    from app.dependencies import get_db

    async def mock_get_db():
        yield mock_session

    client._transport.app.dependency_overrides[get_db] = mock_get_db

    mock_celery_task = MagicMock()
    mock_celery_task.delay.return_value = mock_task

    with patch(
        "app.entities.tasks.reprocess_entities_to_neo4j",
        mock_celery_task,
    ):
        try:
            response = await client.post(
                "/api/v1/admin/knowledge-graph/reprocess",
                json={"document_ids": [str(_DOC_ID_1), str(_DOC_ID_2)]},
            )
        finally:
            del client._transport.app.dependency_overrides[get_db]

    assert response.status_code == 200
    body = response.json()
    assert body["task_id"] == "celery-task-123"
    assert body["document_count"] == 2


@pytest.mark.asyncio
async def test_kg_reprocess_no_ids_400(client: AsyncClient) -> None:
    """Reprocess without document_ids or all_unprocessed returns 400."""
    mock_session = _mock_db_session([])

    from app.dependencies import get_db

    async def mock_get_db():
        yield mock_session

    client._transport.app.dependency_overrides[get_db] = mock_get_db

    try:
        response = await client.post(
            "/api/v1/admin/knowledge-graph/reprocess",
            json={},
        )
    finally:
        del client._transport.app.dependency_overrides[get_db]

    assert response.status_code == 400


# ---------------------------------------------------------------------------
# POST /admin/knowledge-graph/resolve
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_kg_resolve_simple(client: AsyncClient) -> None:
    """Resolve in simple mode dispatches resolve_entities task."""
    mock_task = MagicMock()
    mock_task.id = "resolve-task-456"

    with patch("app.entities.tasks.resolve_entities") as mock_resolve:
        mock_resolve.delay.return_value = mock_task
        response = await client.post(
            "/api/v1/admin/knowledge-graph/resolve",
            json={"mode": "simple"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["task_id"] == "resolve-task-456"
    assert body["mode"] == "simple"


@pytest.mark.asyncio
async def test_kg_resolve_agent(client: AsyncClient) -> None:
    """Resolve in agent mode dispatches entity_resolution_agent task."""
    mock_task = MagicMock()
    mock_task.id = "agent-task-789"

    with patch("app.entities.tasks.entity_resolution_agent") as mock_agent:
        mock_agent.delay.return_value = mock_task
        response = await client.post(
            "/api/v1/admin/knowledge-graph/resolve",
            json={"mode": "agent"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["task_id"] == "agent-task-789"
    assert body["mode"] == "agent"


# ---------------------------------------------------------------------------
# Auth: non-admin gets 403
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_kg_status_non_admin_403(client: AsyncClient) -> None:
    """Non-admin users get 403 on KG status endpoint."""
    from app.auth.middleware import get_current_user

    reviewer_user = UserRecord(
        id=UUID("00000000-0000-0000-0000-000000000077"),
        email="reviewer@nexus.dev",
        full_name="Doc Reviewer",
        role="reviewer",
        is_active=True,
        created_at=datetime.now(UTC),
    )

    client._transport.app.dependency_overrides[get_current_user] = lambda: reviewer_user

    try:
        response = await client.get("/api/v1/admin/knowledge-graph/status")
    finally:
        from tests.conftest import _TEST_USER

        client._transport.app.dependency_overrides[get_current_user] = lambda: _TEST_USER

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_kg_resolve_non_admin_403(client: AsyncClient) -> None:
    """Non-admin users get 403 on KG resolve endpoint."""
    from app.auth.middleware import get_current_user

    reviewer_user = UserRecord(
        id=UUID("00000000-0000-0000-0000-000000000077"),
        email="reviewer@nexus.dev",
        full_name="Doc Reviewer",
        role="reviewer",
        is_active=True,
        created_at=datetime.now(UTC),
    )

    client._transport.app.dependency_overrides[get_current_user] = lambda: reviewer_user

    try:
        response = await client.post(
            "/api/v1/admin/knowledge-graph/resolve",
            json={"mode": "simple"},
        )
    finally:
        from tests.conftest import _TEST_USER

        client._transport.app.dependency_overrides[get_current_user] = lambda: _TEST_USER

    assert response.status_code == 403
