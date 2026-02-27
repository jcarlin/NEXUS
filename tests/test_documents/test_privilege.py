"""Tests for document privilege tagging and enforcement."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient

from app.common.models import PrivilegeStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_doc_row(doc_id=None, **overrides) -> dict:
    """Return a dict mimicking a raw DB row from the documents table."""
    base = {
        "id": doc_id or uuid4(),
        "job_id": uuid4(),
        "filename": "contract.pdf",
        "document_type": "legal_filing",
        "page_count": 10,
        "chunk_count": 25,
        "entity_count": 5,
        "minio_path": "raw/abc/contract.pdf",
        "file_size_bytes": 102400,
        "content_hash": "sha256-abc",
        "metadata_": {},
        "matter_id": UUID("00000000-0000-0000-0000-000000000001"),
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "privilege_status": None,
        "privilege_reviewed_by": None,
        "privilege_reviewed_at": None,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# PATCH /documents/{doc_id}/privilege
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_privilege_attorney_200(client: AsyncClient) -> None:
    """PATCH privilege returns 200 for admin (default test user is admin)."""
    doc_id = uuid4()
    row = _fake_doc_row(doc_id=doc_id)
    reviewed_at = datetime.now(timezone.utc)

    mock_qdrant = MagicMock()
    mock_qdrant.update_privilege_status = AsyncMock()
    mock_gs = MagicMock()
    mock_gs.update_document_privilege = AsyncMock()

    with (
        patch("app.documents.service.DocumentService.get_document", new_callable=AsyncMock, return_value=row),
        patch("app.documents.service.DocumentService.update_privilege", new_callable=AsyncMock, return_value={
            "id": doc_id,
            "privilege_status": "privileged",
            "privilege_reviewed_by": UUID("00000000-0000-0000-0000-000000000099"),
            "privilege_reviewed_at": reviewed_at,
        }),
        patch("app.dependencies._qdrant_client", mock_qdrant),
        patch("app.dependencies._graph_service", mock_gs),
    ):
        response = await client.patch(
            f"/api/v1/documents/{doc_id}/privilege",
            json={"privilege_status": "privileged"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(doc_id)
    assert body["privilege_status"] == "privileged"
    assert body["privilege_reviewed_by"] == "00000000-0000-0000-0000-000000000099"

    # Verify all 3 data layers were updated
    mock_qdrant.update_privilege_status.assert_called_once()
    mock_gs.update_document_privilege.assert_called_once()


@pytest.mark.asyncio
async def test_patch_privilege_paralegal_200(client: AsyncClient) -> None:
    """PATCH privilege returns 200 for paralegal role."""
    from app.auth.middleware import get_current_user

    paralegal_user = {
        "id": UUID("00000000-0000-0000-0000-000000000088"),
        "email": "paralegal@nexus.dev",
        "full_name": "Para Legal",
        "role": "paralegal",
        "is_active": True,
    }

    doc_id = uuid4()
    row = _fake_doc_row(doc_id=doc_id)
    reviewed_at = datetime.now(timezone.utc)

    mock_qdrant = MagicMock()
    mock_qdrant.update_privilege_status = AsyncMock()
    mock_gs = MagicMock()
    mock_gs.update_document_privilege = AsyncMock()

    # Temporarily override the current_user to be a paralegal
    client._transport.app.dependency_overrides[get_current_user] = lambda: paralegal_user

    try:
        with (
            patch("app.documents.service.DocumentService.get_document", new_callable=AsyncMock, return_value=row),
            patch("app.documents.service.DocumentService.update_privilege", new_callable=AsyncMock, return_value={
                "id": doc_id,
                "privilege_status": "work_product",
                "privilege_reviewed_by": paralegal_user["id"],
                "privilege_reviewed_at": reviewed_at,
            }),
            patch("app.dependencies._qdrant_client", mock_qdrant),
            patch("app.dependencies._graph_service", mock_gs),
        ):
            response = await client.patch(
                f"/api/v1/documents/{doc_id}/privilege",
                json={"privilege_status": "work_product"},
            )
    finally:
        # Restore default admin user
        from tests.conftest import _TEST_USER
        client._transport.app.dependency_overrides[get_current_user] = lambda: _TEST_USER

    assert response.status_code == 200
    body = response.json()
    assert body["privilege_status"] == "work_product"


@pytest.mark.asyncio
async def test_patch_privilege_reviewer_403(client: AsyncClient) -> None:
    """PATCH privilege returns 403 for reviewer (excluded role)."""
    from app.auth.middleware import get_current_user

    reviewer_user = {
        "id": UUID("00000000-0000-0000-0000-000000000077"),
        "email": "reviewer@nexus.dev",
        "full_name": "Doc Reviewer",
        "role": "reviewer",
        "is_active": True,
    }

    client._transport.app.dependency_overrides[get_current_user] = lambda: reviewer_user

    try:
        response = await client.patch(
            f"/api/v1/documents/{uuid4()}/privilege",
            json={"privilege_status": "privileged"},
        )
    finally:
        from tests.conftest import _TEST_USER
        client._transport.app.dependency_overrides[get_current_user] = lambda: _TEST_USER

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_patch_privilege_not_found(client: AsyncClient) -> None:
    """PATCH privilege returns 404 for nonexistent document."""
    with patch(
        "app.documents.service.DocumentService.get_document",
        new_callable=AsyncMock,
        return_value=None,
    ):
        response = await client.patch(
            f"/api/v1/documents/{uuid4()}/privilege",
            json={"privilege_status": "not_privileged"},
        )

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# SQL privilege filtering
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reviewer_cannot_see_privileged_docs(client: AsyncClient) -> None:
    """Reviewer's list_documents call passes user_role that excludes privileged docs."""
    from app.auth.middleware import get_current_user

    reviewer_user = {
        "id": UUID("00000000-0000-0000-0000-000000000077"),
        "email": "reviewer@nexus.dev",
        "full_name": "Doc Reviewer",
        "role": "reviewer",
        "is_active": True,
    }

    client._transport.app.dependency_overrides[get_current_user] = lambda: reviewer_user

    try:
        with patch(
            "app.documents.service.DocumentService.list_documents",
            new_callable=AsyncMock,
            return_value=([], 0),
        ) as mock_list:
            await client.get("/api/v1/documents")

        # Verify user_role was passed through
        call_kwargs = mock_list.call_args[1]
        assert call_kwargs["user_role"] == "reviewer"
    finally:
        from tests.conftest import _TEST_USER
        client._transport.app.dependency_overrides[get_current_user] = lambda: _TEST_USER


# ---------------------------------------------------------------------------
# Qdrant privilege filtering
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_qdrant_query_builds_must_not_filter() -> None:
    """query_text() builds must_not conditions for excluded privilege statuses."""
    from unittest.mock import MagicMock
    from app.common.vector_store import VectorStoreClient
    from qdrant_client.models import FieldCondition, MatchValue

    mock_settings = MagicMock()
    mock_settings.qdrant_url = "http://localhost:6333"
    mock_settings.embedding_dimensions = 1024
    mock_settings.enable_visual_embeddings = False
    mock_settings.enable_sparse_embeddings = False

    with patch("app.common.vector_store.QdrantClient"):
        vs = VectorStoreClient(mock_settings)

    mock_result = MagicMock()
    mock_result.points = []
    vs.client.query_points = MagicMock(return_value=mock_result)

    await vs.query_text(
        vector=[0.1] * 1024,
        limit=10,
        filters={"matter_id": "test-matter"},
        exclude_privilege_statuses=["privileged", "work_product"],
    )

    # Check the filter was built with must_not
    call_kwargs = vs.client.query_points.call_args[1]
    qdrant_filter = call_kwargs.get("query_filter")
    assert qdrant_filter is not None
    assert qdrant_filter.must_not is not None
    assert len(qdrant_filter.must_not) == 2


# ---------------------------------------------------------------------------
# Neo4j privilege filtering
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_graph_connections_includes_privilege_exclusion() -> None:
    """get_entity_connections() Cypher includes privilege exclusion when specified."""
    from app.entities.graph_service import GraphService

    mock_driver = MagicMock()
    gs = GraphService(mock_driver)

    # Patch _run_query to capture the query string
    captured_queries: list[str] = []

    async def fake_run_query(query: str, params=None):
        captured_queries.append(query)
        return []

    gs._run_query = fake_run_query

    await gs.get_entity_connections(
        "John Doe",
        limit=50,
        exclude_privilege_statuses=["privileged", "work_product"],
    )

    assert len(captured_queries) == 1
    cypher = captured_queries[0]
    assert "privilege_status" in cypher
    assert "excluded_statuses" in cypher
