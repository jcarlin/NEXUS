"""Tests for T3-12: Automatic V1/Agentic Graph Routing."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.query.nodes import classify_tier


class TestClassifyTier:
    """Test the classify_tier heuristic."""

    def test_fast_tier_who_question(self):
        assert classify_tier("Who is Jeffrey Epstein?") == "fast"

    def test_fast_tier_what_question(self):
        assert classify_tier("What is the settlement amount?") == "fast"

    def test_standard_tier_moderate_query(self):
        assert classify_tier("Tell me about the financial transactions involving the trust fund") == "standard"

    def test_deep_tier_comparison(self):
        assert classify_tier("Compare the testimony of witness A with the deposition from witness B") == "deep"

    def test_deep_tier_timeline(self):
        assert classify_tier("timeline of all communications between 2005 and 2008") == "deep"

    def test_deep_tier_long_query(self):
        long_query = " ".join(["word"] * 35)
        assert classify_tier(long_query) == "deep"


class TestAutoRouting:
    """Test auto-routing logic."""

    @pytest.fixture
    def mock_settings(self):
        settings = MagicMock()
        settings.enable_auto_graph_routing = True
        settings.enable_agentic_pipeline = True
        settings.enable_citation_verification = True
        settings.enable_production_quality_monitoring = False
        return settings

    def test_fast_query_routes_to_v1(self, mock_settings):
        """Fast queries should use V1 graph when auto-routing is enabled."""
        tier = classify_tier("Who is the CEO?")
        use_agentic = tier != "fast"
        assert use_agentic is False

    def test_deep_query_routes_to_agentic(self, mock_settings):
        """Deep queries should use agentic graph."""
        tier = classify_tier("Compare all financial transactions with the trust records")
        use_agentic = tier != "fast"
        assert use_agentic is True

    def test_standard_query_routes_to_agentic(self, mock_settings):
        """Standard queries should use agentic graph."""
        tier = classify_tier("Describe the relationship between the two companies")
        use_agentic = tier != "fast"
        assert use_agentic is True


# ---------------------------------------------------------------------------
# Graph selection integration tests — verify the correct graph is invoked
# ---------------------------------------------------------------------------

_V1_RESPONSE_STATE = {
    "response": "V1 test response [Source: doc.pdf, page 1]",
    "source_documents": [
        {
            "id": "p1",
            "filename": "doc.pdf",
            "page": 1,
            "chunk_text": "test chunk",
            "relevance_score": 0.9,
            "preview_url": None,
            "download_url": None,
        }
    ],
    "follow_up_questions": ["Follow up?"],
    "entities_mentioned": [{"name": "Test", "type": "person", "kg_id": None, "connections": 0}],
}

_AGENTIC_RESPONSE_STATE = {
    "messages": [MagicMock(content="Agentic test response")],
    "source_documents": _V1_RESPONSE_STATE["source_documents"],
    "follow_up_questions": ["Follow up?"],
    "entities_mentioned": _V1_RESPONSE_STATE["entities_mentioned"],
    "cited_claims": [],
    "entity_grounding": [],
    "_tier": "standard",
    "_query_type": "factual",
}


def _mock_settings_auto_routing():
    """Settings with auto-routing + agentic pipeline both enabled."""
    s = MagicMock()
    s.enable_agentic_pipeline = True
    s.enable_auto_graph_routing = True
    s.enable_case_setup_agent = False
    s.enable_citation_verification = False
    s.enable_production_quality_monitoring = False
    s.enable_hallugraph_alignment = False
    s.enable_hyde = False
    s.enable_multi_query_expansion = False
    s.enable_adaptive_retrieval_depth = False
    s.enable_text_to_sql = False
    s.enable_text_to_cypher = False
    s.enable_question_decomposition = False
    s.enable_prompt_routing = False
    s.enable_self_reflection = False
    s.enable_retrieval_grading = False
    s.enable_reranker = False
    s.query_timeout_seconds = 120
    s.max_concurrent_queries = 10
    s.max_query_length = 2000
    return s


@pytest.fixture()
async def auto_routing_client():
    """Async test client configured with auto-routing enabled, two separate mock graphs."""
    from app import main as main_module

    async def _noop_lifespan(app):
        yield

    with patch.object(main_module, "lifespan", _noop_lifespan):
        test_app = main_module.create_app()

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock()
        mock_db.commit = AsyncMock()

        # Two separate graph mocks so we can verify which one was called
        mock_agentic_graph = AsyncMock()
        mock_agentic_graph.ainvoke.return_value = _AGENTIC_RESPONSE_STATE

        mock_v1_graph = AsyncMock()
        mock_v1_graph.ainvoke.return_value = _V1_RESPONSE_STATE

        from app import dependencies
        from app.auth.middleware import get_current_user, get_matter_id
        from app.auth.schemas import UserRecord
        from app.common.rate_limit import rate_limit_queries

        async def mock_get_db():
            yield mock_db

        test_app.dependency_overrides[dependencies.get_db] = mock_get_db
        test_app.dependency_overrides[dependencies.get_query_graph] = lambda: mock_agentic_graph
        test_app.dependency_overrides[rate_limit_queries] = lambda: None
        test_app.dependency_overrides[get_current_user] = lambda: UserRecord(
            id=uuid.UUID("00000000-0000-0000-0000-000000000099"),
            email="test@nexus.dev",
            full_name="Test",
            role="admin",
            is_active=True,
            created_at=datetime(2025, 1, 1, tzinfo=UTC),
        )
        test_app.dependency_overrides[get_matter_id] = lambda: uuid.UUID("00000000-0000-0000-0000-000000000001")

        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            yield ac, mock_db, mock_agentic_graph, mock_v1_graph


@pytest.mark.asyncio
async def test_auto_routing_fast_query_uses_v1_graph(auto_routing_client):
    """When auto-routing is enabled, a fast-tier query should invoke the V1 graph, not the agentic graph."""
    client, mock_db, mock_agentic_graph, mock_v1_graph = auto_routing_client

    with (
        patch("app.dependencies.get_settings", return_value=_mock_settings_auto_routing()),
        patch("app.dependencies.get_query_graph_v1", return_value=mock_v1_graph),
    ):
        response = await client.post("/api/v1/query", json={"query": "Who is John?"})

    assert response.status_code == 200
    # V1 graph should have been called, NOT the agentic graph
    mock_v1_graph.ainvoke.assert_called_once()
    mock_agentic_graph.ainvoke.assert_not_called()


@pytest.mark.asyncio
async def test_auto_routing_deep_query_uses_agentic_graph(auto_routing_client):
    """When auto-routing is enabled, a deep-tier query should invoke the agentic graph."""
    client, mock_db, mock_agentic_graph, mock_v1_graph = auto_routing_client

    with (
        patch("app.dependencies.get_settings", return_value=_mock_settings_auto_routing()),
        patch("app.dependencies.get_query_graph_v1", return_value=mock_v1_graph),
    ):
        response = await client.post(
            "/api/v1/query",
            json={"query": "Compare the testimony of witness A with the deposition from witness B"},
        )

    assert response.status_code == 200
    # Agentic graph should have been called, NOT V1
    mock_agentic_graph.ainvoke.assert_called_once()
    mock_v1_graph.ainvoke.assert_not_called()


@pytest.mark.asyncio
async def test_auto_routing_standard_query_uses_agentic_graph(auto_routing_client):
    """Standard-tier queries should route to the agentic graph."""
    client, mock_db, mock_agentic_graph, mock_v1_graph = auto_routing_client

    with (
        patch("app.dependencies.get_settings", return_value=_mock_settings_auto_routing()),
        patch("app.dependencies.get_query_graph_v1", return_value=mock_v1_graph),
    ):
        response = await client.post(
            "/api/v1/query",
            json={"query": "Tell me about the financial transactions involving the trust fund"},
        )

    assert response.status_code == 200
    mock_agentic_graph.ainvoke.assert_called_once()
    mock_v1_graph.ainvoke.assert_not_called()


@pytest.mark.asyncio
async def test_auto_routing_produces_valid_response(auto_routing_client):
    """Both V1 and agentic paths should produce a valid QueryResponse schema."""
    client, mock_db, mock_agentic_graph, mock_v1_graph = auto_routing_client

    with (
        patch("app.dependencies.get_settings", return_value=_mock_settings_auto_routing()),
        patch("app.dependencies.get_query_graph_v1", return_value=mock_v1_graph),
    ):
        # Fast query → V1
        resp = await client.post("/api/v1/query", json={"query": "Who is John?"})
        assert resp.status_code == 200
        data = resp.json()
        assert "response" in data
        assert "source_documents" in data
        assert "thread_id" in data
