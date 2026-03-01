"""Tests for agentic pipeline node functions (case context resolution, follow-ups)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from app.query.nodes import case_context_resolve, generate_follow_ups_agentic


async def test_case_context_resolve_loads_context():
    """case_context_resolve loads case context and sets tier/term_map."""
    mock_db = AsyncMock()

    async def _fake_get_db():
        yield mock_db

    mock_ctx = {
        "claims": [{"claim_number": 1, "claim_label": "Fraud"}],
        "parties": [{"name": "Smith", "role": "defendant", "aliases": ["Defendant A"]}],
        "defined_terms": [{"term": "Agreement", "definition": "The MSA"}],
        "timeline": [],
    }

    with (
        patch("app.dependencies.get_db", _fake_get_db),
        patch("app.cases.context_resolver.CaseContextResolver") as mock_resolver_cls,
        patch("app.dependencies.get_settings") as mock_get_settings,
    ):
        mock_resolver_cls.get_context_for_matter = AsyncMock(return_value=mock_ctx)
        mock_resolver_cls.format_context_for_prompt = MagicMock(return_value="CASE CONTEXT")
        mock_resolver_cls.build_term_map = MagicMock(return_value={"defendant a": "Smith (defendant)"})

        mock_settings = MagicMock()
        mock_settings.enable_citation_verification = True
        mock_get_settings.return_value = mock_settings

        state = {
            "_filters": {"matter_id": "test-matter"},
            "original_query": "Who is John?",
        }

        result = await case_context_resolve(state)

    assert result["_case_context"] == "CASE CONTEXT"
    assert result["_term_map"] == {"defendant a": "Smith (defendant)"}
    assert result["_tier"] in ("fast", "standard", "deep")
    assert "_skip_verification" in result


async def test_generate_follow_ups_agentic_returns_questions():
    """generate_follow_ups_agentic generates follow-up questions from the response."""
    mock_llm = AsyncMock()
    mock_llm.complete.return_value = (
        "What other documents mention John Doe?\n"
        "Are there financial connections between the parties?\n"
        "What is the chronological timeline of events?"
    )

    state = {
        "response": "John Doe was mentioned in several documents.",
        "original_query": "Who is John Doe?",
        "entities_mentioned": [{"name": "John Doe"}],
        "messages": [],
    }

    with patch("app.dependencies.get_llm", return_value=mock_llm):
        result = await generate_follow_ups_agentic(state)

    assert "follow_up_questions" in result
    assert len(result["follow_up_questions"]) == 3
    assert "John Doe" in result["follow_up_questions"][0]
