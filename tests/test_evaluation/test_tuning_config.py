"""Tests for M15 retrieval tuning config parameters."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch


class TestTunedParametersLoadFromConfig:
    """Verify that the 4 new retrieval tuning settings load correctly and
    thread through to the retrieval components."""

    def test_settings_have_defaults(self) -> None:
        """All 4 tuning settings exist with correct default values."""
        from app.config import Settings

        s = Settings(
            anthropic_api_key="test",
            openai_api_key="test",
            _env_file=None,
        )
        assert s.retrieval_text_limit == 40
        assert s.retrieval_graph_limit == 20
        assert s.retrieval_prefetch_multiplier == 2
        assert s.query_entity_threshold == 0.5

    def test_settings_can_be_overridden(self) -> None:
        """Tuning settings can be overridden via constructor (simulating env vars)."""
        from app.config import Settings

        s = Settings(
            anthropic_api_key="test",
            openai_api_key="test",
            retrieval_text_limit=30,
            retrieval_graph_limit=15,
            retrieval_prefetch_multiplier=4,
            query_entity_threshold=0.3,
            _env_file=None,
        )
        assert s.retrieval_text_limit == 30
        assert s.retrieval_graph_limit == 15
        assert s.retrieval_prefetch_multiplier == 4
        assert s.query_entity_threshold == 0.3

    def test_vector_store_accepts_prefetch_multiplier(self) -> None:
        """VectorStoreClient.query_text() accepts the prefetch_multiplier param."""
        # Check signature accepts the param (no actual Qdrant call)
        import inspect

        from app.common.vector_store import VectorStoreClient

        sig = inspect.signature(VectorStoreClient.query_text)
        assert "prefetch_multiplier" in sig.parameters
        param = sig.parameters["prefetch_multiplier"]
        assert param.default == 2

    def test_retriever_accepts_entity_threshold(self) -> None:
        """HybridRetriever.extract_query_entities() accepts entity_threshold param."""
        import inspect

        from app.query.retriever import HybridRetriever

        sig = inspect.signature(HybridRetriever.extract_query_entities)
        assert "entity_threshold" in sig.parameters

    def test_retrieve_node_uses_settings(self) -> None:
        """The retrieve node reads limits from Settings, not hardcoded values."""
        import asyncio

        from app.query.nodes import create_nodes

        mock_llm = MagicMock()
        mock_retriever = MagicMock()
        mock_retriever.retrieve_all = AsyncMock(return_value=([], []))
        mock_graph = MagicMock()
        mock_extractor = MagicMock()

        nodes = create_nodes(mock_llm, mock_retriever, mock_graph, mock_extractor)
        retrieve_fn = nodes["retrieve"]

        state = {"original_query": "test query", "_filters": None, "_exclude_privilege": []}

        with patch("app.dependencies.get_settings") as mock_settings:
            settings = MagicMock()
            settings.retrieval_text_limit = 30
            settings.retrieval_graph_limit = 15
            settings.retrieval_prefetch_multiplier = 3
            settings.query_entity_threshold = 0.4
            mock_settings.return_value = settings

            asyncio.run(retrieve_fn(state))

        mock_retriever.retrieve_all.assert_called_once()
        call_kwargs = mock_retriever.retrieve_all.call_args
        assert call_kwargs.kwargs["text_limit"] == 30
        assert call_kwargs.kwargs["graph_limit"] == 15
        assert call_kwargs.kwargs["prefetch_multiplier"] == 3
        assert call_kwargs.kwargs["entity_threshold"] == 0.4
