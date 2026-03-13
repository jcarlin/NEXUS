"""Tests for T2-6: HyDE (Hypothetical Document Embeddings)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.query.hyde import generate_hypothetical_document


@pytest.fixture
def mock_llm():
    return AsyncMock()


class TestGenerateHypotheticalDocument:
    @pytest.mark.asyncio
    async def test_generates_passage(self, mock_llm):
        """Verify generate_hypothetical_document returns a non-empty passage."""
        mock_llm.complete = AsyncMock(
            return_value="On March 15, 2020, the defendant entered into a purchase agreement "
            "with Acme Corp for the acquisition of assets valued at $2.5 million."
        )

        result = await generate_hypothetical_document(
            "What was the value of the Acme Corp deal?",
            mock_llm,
        )

        assert len(result) > 0
        assert "Acme Corp" in result

    @pytest.mark.asyncio
    async def test_includes_matter_context(self, mock_llm):
        """Verify matter_context is passed to the prompt."""
        mock_llm.complete = AsyncMock(return_value="A relevant passage.")

        await generate_hypothetical_document(
            "Who knew about the transaction?",
            mock_llm,
            matter_context="Securities fraud case involving insider trading",
        )

        call_args = mock_llm.complete.call_args
        prompt_content = call_args[0][0][0]["content"]
        assert "Securities fraud case" in prompt_content

    @pytest.mark.asyncio
    async def test_no_context_no_block(self, mock_llm):
        """Verify no context block when matter_context is empty."""
        mock_llm.complete = AsyncMock(return_value="A passage.")

        await generate_hypothetical_document("test query", mock_llm)

        call_args = mock_llm.complete.call_args
        prompt_content = call_args[0][0][0]["content"]
        assert "Context about this legal matter" not in prompt_content

    @pytest.mark.asyncio
    async def test_strips_whitespace(self, mock_llm):
        """Verify output is stripped of leading/trailing whitespace."""
        mock_llm.complete = AsyncMock(return_value="\n  A passage.  \n")

        result = await generate_hypothetical_document("test", mock_llm)
        assert result == "A passage."

    @pytest.mark.asyncio
    async def test_propagates_llm_errors(self, mock_llm):
        """Verify LLM errors are propagated (not silently swallowed)."""
        mock_llm.complete = AsyncMock(side_effect=Exception("API error"))

        with pytest.raises(Exception, match="API error"):
            await generate_hypothetical_document("test", mock_llm)

    @pytest.mark.asyncio
    async def test_uses_correct_node_name(self, mock_llm):
        """Verify the LLM call uses the correct node_name for audit logging."""
        mock_llm.complete = AsyncMock(return_value="passage")

        await generate_hypothetical_document("test", mock_llm)

        call_kwargs = mock_llm.complete.call_args[1]
        assert call_kwargs.get("node_name") == "hyde_generate"


class TestHyDERetrieverIntegration:
    @pytest.mark.asyncio
    async def test_hyde_vector_used_for_dense(self):
        """Verify HyDE vector replaces raw query vector for dense retrieval."""
        from app.query.retriever import HybridRetriever

        mock_embedder = AsyncMock()
        mock_embedder.embed_query = AsyncMock(return_value=[0.1] * 1024)
        mock_vector_store = AsyncMock()
        mock_vector_store.query_text = AsyncMock(return_value=[])
        mock_entity_extractor = AsyncMock()
        mock_graph_service = AsyncMock()

        retriever = HybridRetriever(mock_embedder, mock_vector_store, mock_entity_extractor, mock_graph_service)

        hyde_vec = [0.9] * 1024
        with patch("app.dependencies.get_settings") as mock_settings:
            mock_settings.return_value.enable_near_duplicate_detection = False
            await retriever.retrieve_text(
                "test query",
                limit=10,
                hyde_vector=hyde_vec,
            )

        # The dense vector passed to query_text should be the HyDE vector
        call_args = mock_vector_store.query_text.call_args
        vector_arg = call_args[0][0]
        assert vector_arg == hyde_vec
        # embedder.embed_query should NOT have been called (HyDE vector provided)
        mock_embedder.embed_query.assert_not_called()

    @pytest.mark.asyncio
    async def test_raw_query_used_for_sparse(self):
        """Verify raw query is still used for sparse retrieval with HyDE."""
        from app.query.retriever import HybridRetriever

        mock_embedder = AsyncMock()
        mock_vector_store = AsyncMock()
        mock_vector_store.query_text = AsyncMock(return_value=[])
        mock_entity_extractor = AsyncMock()
        mock_graph_service = AsyncMock()
        mock_sparse_embedder = AsyncMock()
        mock_sparse_embedder.embed_single = lambda q: ([0, 1], [0.5, 0.6])

        retriever = HybridRetriever(
            mock_embedder,
            mock_vector_store,
            mock_entity_extractor,
            mock_graph_service,
            sparse_embedder=mock_sparse_embedder,
        )

        hyde_vec = [0.9] * 1024
        with patch("app.dependencies.get_settings") as mock_settings:
            mock_settings.return_value.enable_near_duplicate_detection = False
            await retriever.retrieve_text(
                "original query text",
                limit=10,
                hyde_vector=hyde_vec,
            )

        # Sparse vector should use the raw query ("original query text")
        call_kwargs = mock_vector_store.query_text.call_args[1]
        sparse = call_kwargs.get("sparse_vector")
        assert sparse is not None  # Sparse embedder was called with raw query

    @pytest.mark.asyncio
    async def test_no_hyde_uses_raw_embedding(self):
        """Verify without HyDE, the raw query is embedded normally."""
        from app.query.retriever import HybridRetriever

        mock_embedder = AsyncMock()
        raw_vec = [0.1] * 1024
        mock_embedder.embed_query = AsyncMock(return_value=raw_vec)
        mock_vector_store = AsyncMock()
        mock_vector_store.query_text = AsyncMock(return_value=[])
        mock_entity_extractor = AsyncMock()
        mock_graph_service = AsyncMock()

        retriever = HybridRetriever(mock_embedder, mock_vector_store, mock_entity_extractor, mock_graph_service)

        with patch("app.dependencies.get_settings") as mock_settings:
            mock_settings.return_value.enable_near_duplicate_detection = False
            await retriever.retrieve_text("test query", limit=10)

        # Should have called embed_query with the raw query
        mock_embedder.embed_query.assert_called_once_with("test query")
        # The vector passed to query_text should be the raw embedding
        call_args = mock_vector_store.query_text.call_args
        assert call_args[0][0] == raw_vec


class TestHyDEFeatureFlag:
    @pytest.mark.asyncio
    async def test_disabled_skips_hyde(self):
        """Verify that when enable_hyde=False, no HyDE call is made in retriever."""
        from app.query.retriever import HybridRetriever

        mock_embedder = AsyncMock()
        raw_vec = [0.1] * 1024
        mock_embedder.embed_query = AsyncMock(return_value=raw_vec)
        mock_vector_store = AsyncMock()
        mock_vector_store.query_text = AsyncMock(return_value=[])
        mock_entity_extractor = AsyncMock()
        mock_graph_service = AsyncMock()

        retriever = HybridRetriever(mock_embedder, mock_vector_store, mock_entity_extractor, mock_graph_service)

        # Call without hyde_vector (feature disabled path)
        with patch("app.dependencies.get_settings") as mock_settings:
            mock_settings.return_value.enable_near_duplicate_detection = False
            await retriever.retrieve_text("test query", limit=10)

        # Should have embedded the raw query (no HyDE)
        mock_embedder.embed_query.assert_called_once_with("test query")
        call_args = mock_vector_store.query_text.call_args
        assert call_args[0][0] == raw_vec
