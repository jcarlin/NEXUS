"""Tests for T3-13: Adaptive Retrieval Depth."""

from unittest.mock import patch


class TestAdaptiveDepthConfig:
    """Test adaptive depth configuration."""

    def test_default_depths(self):
        with patch.dict("os.environ", {}, clear=True):
            from app.config import Settings

            s = Settings()
            assert s.retrieval_depth_factual_text == 15
            assert s.retrieval_depth_factual_graph == 8
            assert s.retrieval_depth_analytical_text == 30
            assert s.retrieval_depth_analytical_graph == 15
            assert s.retrieval_depth_comparative_text == 35
            assert s.retrieval_depth_comparative_graph == 20
            assert s.retrieval_depth_temporal_text == 25
            assert s.retrieval_depth_temporal_graph == 12
            assert s.retrieval_depth_procedural_text == 20
            assert s.retrieval_depth_procedural_graph == 10
            assert s.retrieval_depth_exploratory_text == 40
            assert s.retrieval_depth_exploratory_graph == 20

    def test_feature_flag_default_off(self):
        with patch.dict("os.environ", {}, clear=True):
            from app.config import Settings

            s = Settings()
            assert s.enable_adaptive_retrieval_depth is False

    def test_depth_lookup_by_query_type(self):
        """getattr-based lookup should work for all query types."""
        from app.config import Settings

        s = Settings()
        for qt in ["factual", "analytical", "comparative", "temporal", "procedural", "exploratory"]:
            text_val = getattr(s, f"retrieval_depth_{qt}_text")
            graph_val = getattr(s, f"retrieval_depth_{qt}_graph")
            assert isinstance(text_val, int) and text_val > 0
            assert isinstance(graph_val, int) and graph_val > 0

    def test_fallback_for_unknown_type(self):
        """Unknown query type should fall back to default limits."""
        from app.config import Settings

        s = Settings()
        text_val = getattr(s, "retrieval_depth_unknown_text", s.retrieval_text_limit)
        assert text_val == s.retrieval_text_limit


class TestAdaptiveDepthLogic:
    """Test the adaptive depth selection logic."""

    def test_factual_gets_shallow_depth(self):
        from app.config import Settings

        s = Settings()
        query_type = "factual"
        text_limit = getattr(s, f"retrieval_depth_{query_type}_text", s.retrieval_text_limit)
        graph_limit = getattr(s, f"retrieval_depth_{query_type}_graph", s.retrieval_graph_limit)
        assert text_limit == 15  # Shallower than default 40
        assert graph_limit == 8  # Shallower than default 20

    def test_exploratory_gets_deep_depth(self):
        from app.config import Settings

        s = Settings()
        query_type = "exploratory"
        text_limit = getattr(s, f"retrieval_depth_{query_type}_text", s.retrieval_text_limit)
        assert text_limit == 40  # Same as default — exploratory needs maximum

    def test_comparative_gets_wide_depth(self):
        from app.config import Settings

        s = Settings()
        query_type = "comparative"
        text_limit = getattr(s, f"retrieval_depth_{query_type}_text", s.retrieval_text_limit)
        graph_limit = getattr(s, f"retrieval_depth_{query_type}_graph", s.retrieval_graph_limit)
        assert text_limit == 35
        assert graph_limit == 20


class TestCaseContextResolveAdaptiveDepth:
    """Test that case_context_resolve sets adaptive limits in state."""

    async def test_adaptive_limits_set_for_known_query_type(self):
        """When adaptive depth is enabled, limits should be set from query type."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from app.query.nodes import case_context_resolve

        async def _fake_get_db():
            yield AsyncMock()

        mock_settings = MagicMock()
        mock_settings.enable_citation_verification = True
        mock_settings.enable_prompt_routing = False
        mock_settings.enable_adaptive_retrieval_depth = True
        mock_settings.retrieval_depth_factual_text = 15
        mock_settings.retrieval_depth_factual_graph = 8
        mock_settings.retrieval_text_limit = 40
        mock_settings.retrieval_graph_limit = 20

        with (
            patch("app.dependencies.get_db", _fake_get_db),
            patch("app.dependencies.get_settings", return_value=mock_settings),
        ):
            state = {
                "_filters": {"matter_id": "test-matter"},
                "original_query": "Who is John?",
            }
            result = await case_context_resolve(state)

        # Default query_type is "factual" when prompt routing is off
        assert result["_adaptive_text_limit"] == 15
        assert result["_adaptive_graph_limit"] == 8

    async def test_adaptive_limits_none_when_disabled(self):
        """When adaptive depth is disabled, limits should be None."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from app.query.nodes import case_context_resolve

        async def _fake_get_db():
            yield AsyncMock()

        mock_settings = MagicMock()
        mock_settings.enable_citation_verification = True
        mock_settings.enable_prompt_routing = False
        mock_settings.enable_adaptive_retrieval_depth = False

        with (
            patch("app.dependencies.get_db", _fake_get_db),
            patch("app.dependencies.get_settings", return_value=mock_settings),
        ):
            state = {
                "_filters": {"matter_id": "test-matter"},
                "original_query": "Who is John?",
            }
            result = await case_context_resolve(state)

        assert result["_adaptive_text_limit"] is None
        assert result["_adaptive_graph_limit"] is None
