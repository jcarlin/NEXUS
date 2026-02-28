"""Tests for query prompt templates."""

from app.query.prompts import (
    CLASSIFY_PROMPT,
    FOLLOWUP_PROMPT,
    REWRITE_PROMPT,
    SYNTHESIS_PROMPT,
)


def test_classify_prompt_has_query_placeholder():
    assert "{query}" in CLASSIFY_PROMPT


def test_classify_prompt_lists_categories():
    for category in ("factual", "analytical", "exploratory", "timeline"):
        assert category in CLASSIFY_PROMPT


def test_rewrite_prompt_has_required_placeholders():
    assert "{history}" in REWRITE_PROMPT
    assert "{query}" in REWRITE_PROMPT


def test_synthesis_prompt_has_required_placeholders():
    assert "{context}" in SYNTHESIS_PROMPT
    assert "{graph_context}" in SYNTHESIS_PROMPT
    assert "{query}" in SYNTHESIS_PROMPT


def test_synthesis_prompt_mentions_citations():
    assert "[Source:" in SYNTHESIS_PROMPT


def test_followup_prompt_has_required_placeholders():
    assert "{query}" in FOLLOWUP_PROMPT
    assert "{response}" in FOLLOWUP_PROMPT
    assert "{entities}" in FOLLOWUP_PROMPT


def test_followup_prompt_requests_three_questions():
    assert "3" in FOLLOWUP_PROMPT


def test_rewrite_prompt_has_case_context_placeholder():
    assert "{case_context}" in REWRITE_PROMPT


def test_synthesis_prompt_has_case_context_placeholder():
    assert "{case_context}" in SYNTHESIS_PROMPT


def test_prompts_are_formattable():
    """Verify all prompts can be formatted without KeyError."""
    CLASSIFY_PROMPT.format(query="test query")
    REWRITE_PROMPT.format(history="User: hello", query="test", case_context="")
    SYNTHESIS_PROMPT.format(context="evidence", graph_context="graph", query="test", case_context="")
    FOLLOWUP_PROMPT.format(query="test", response="answer", entities="person A")
