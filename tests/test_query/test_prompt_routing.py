"""Tests for T1-6: Semantic prompt routing."""

from __future__ import annotations

from app.query.prompts import (
    ANALYTICAL_ADDENDUM,
    EXPLORATORY_ADDENDUM,
    FACTUAL_ADDENDUM,
    PROMPT_ROUTING_MAP,
    TIMELINE_ADDENDUM,
)


class TestPromptRoutingMap:
    """Tests for prompt routing configuration."""

    def test_all_categories_mapped(self):
        assert "factual" in PROMPT_ROUTING_MAP
        assert "analytical" in PROMPT_ROUTING_MAP
        assert "exploratory" in PROMPT_ROUTING_MAP
        assert "timeline" in PROMPT_ROUTING_MAP

    def test_addenda_are_non_empty(self):
        assert len(FACTUAL_ADDENDUM) > 20
        assert len(ANALYTICAL_ADDENDUM) > 20
        assert len(EXPLORATORY_ADDENDUM) > 20
        assert len(TIMELINE_ADDENDUM) > 20


class TestBuildSystemPrompt:
    """Tests for build_system_prompt with routing."""

    def test_routes_factual_correctly(self):
        from app.query.nodes import build_system_prompt

        state = {"_case_context": "", "_query_type": "factual", "messages": []}
        result = build_system_prompt(state)
        system_text = result[0].content
        assert "Factual Lookup" in system_text

    def test_routes_analytical_correctly(self):
        from app.query.nodes import build_system_prompt

        state = {"_case_context": "", "_query_type": "analytical", "messages": []}
        result = build_system_prompt(state)
        system_text = result[0].content
        assert "Analytical" in system_text

    def test_routes_timeline_correctly(self):
        from app.query.nodes import build_system_prompt

        state = {"_case_context": "", "_query_type": "timeline", "messages": []}
        result = build_system_prompt(state)
        system_text = result[0].content
        assert "Timeline" in system_text

    def test_routes_exploratory_correctly(self):
        from app.query.nodes import build_system_prompt

        state = {"_case_context": "", "_query_type": "exploratory", "messages": []}
        result = build_system_prompt(state)
        system_text = result[0].content
        assert "Exploratory" in system_text

    def test_fallback_no_query_type(self):
        """When no query type is set, base prompt is used without addendum."""
        from app.query.nodes import build_system_prompt

        state = {"_case_context": "", "messages": []}
        result = build_system_prompt(state)
        system_text = result[0].content
        # Should not contain any addendum markers
        assert "Query Type:" not in system_text

    def test_unknown_query_type_falls_back(self):
        """Unknown query type should use base prompt only."""
        from app.query.nodes import build_system_prompt

        state = {"_case_context": "", "_query_type": "unknown_type", "messages": []}
        result = build_system_prompt(state)
        system_text = result[0].content
        assert "Query Type:" not in system_text

    def test_routing_preserves_case_context(self):
        """Prompt routing should work alongside case context injection."""
        from app.query.nodes import build_system_prompt

        state = {
            "_case_context": "## Case: Smith v. Jones",
            "_query_type": "factual",
            "messages": [],
        }
        result = build_system_prompt(state)
        system_text = result[0].content
        assert "Smith v. Jones" in system_text
        assert "Factual Lookup" in system_text
