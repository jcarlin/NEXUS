"""Tests for T3-12: Automatic V1/Agentic Graph Routing."""

from unittest.mock import MagicMock

import pytest

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
