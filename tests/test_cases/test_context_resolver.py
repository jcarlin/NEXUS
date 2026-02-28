"""Tests for CaseContextResolver: term mapping, reference expansion, prompt formatting."""

from __future__ import annotations

import pytest

from app.cases.context_resolver import CaseContextResolver


@pytest.fixture()
def sample_context() -> dict:
    """Return a sample case context dict mimicking CaseService.get_full_context output."""
    return {
        "id": "11111111-1111-1111-1111-111111111111",
        "matter_id": "00000000-0000-0000-0000-000000000001",
        "status": "confirmed",
        "anchor_document_id": "raw/abc/complaint.pdf",
        "claims": [
            {
                "id": "claim-1",
                "claim_number": 1,
                "claim_label": "Fraud",
                "claim_text": "Defendant committed fraud by misrepresenting material facts.",
                "legal_elements": ["intent", "misrepresentation"],
                "source_pages": [3, 4],
            },
            {
                "id": "claim-2",
                "claim_number": 2,
                "claim_label": "Breach of Fiduciary Duty",
                "claim_text": "Defendant breached fiduciary duties owed to plaintiff.",
                "legal_elements": ["fiduciary relationship", "breach"],
                "source_pages": [8],
            },
        ],
        "parties": [
            {
                "id": "party-1",
                "name": "John Smith",
                "role": "plaintiff",
                "description": "Individual investor",
                "aliases": ["Smith", "Plaintiff"],
                "entity_id": None,
                "source_pages": [1],
            },
            {
                "id": "party-2",
                "name": "Acme Corporation",
                "role": "defendant",
                "description": "Delaware corporation",
                "aliases": ["Acme", "the Company", "Defendant A"],
                "entity_id": None,
                "source_pages": [1, 2],
            },
        ],
        "defined_terms": [
            {
                "id": "term-1",
                "term": "the Agreement",
                "definition": "The Stock Purchase Agreement dated January 1, 2020",
                "entity_id": None,
                "source_pages": [2],
            },
            {
                "id": "term-2",
                "term": "Closing Date",
                "definition": "March 15, 2020",
                "entity_id": None,
                "source_pages": [4],
            },
        ],
        "timeline": [
            {
                "date": "January 1, 2020",
                "event_text": "Agreement signed",
                "source_page": 2,
            },
            {
                "date": "March 15, 2020",
                "event_text": "Closing completed",
                "source_page": 5,
            },
        ],
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-01T00:00:00",
    }


def test_build_term_map_includes_all_sources(sample_context):
    """Term map includes defined terms, party aliases, and claim references."""
    term_map = CaseContextResolver.build_term_map(sample_context)

    # Defined terms
    assert "the agreement" in term_map
    assert "Stock Purchase Agreement" in term_map["the agreement"]

    assert "closing date" in term_map
    assert "March 15, 2020" in term_map["closing date"]

    # Party aliases
    assert "the company" in term_map
    assert "Acme Corporation" in term_map["the company"]

    assert "defendant a" in term_map
    assert "Acme Corporation" in term_map["defendant a"]

    assert "smith" in term_map
    assert "John Smith" in term_map["smith"]

    # Claim references
    assert "claim 1" in term_map
    assert "Fraud" in term_map["claim 1"]

    assert "claim 2" in term_map
    assert "Breach of Fiduciary Duty" in term_map["claim 2"]

    # Roman numeral variants
    assert "count i" in term_map
    assert "count ii" in term_map


def test_expand_references_replaces_known_terms(sample_context):
    """expand_references appends context when known terms are found in query."""
    term_map = CaseContextResolver.build_term_map(sample_context)

    # Query mentioning a defined term
    query = "What did the Company do before the Closing Date?"
    expanded = CaseContextResolver.expand_references(query, term_map)

    # Original query is preserved
    assert query in expanded

    # Expansions are appended
    assert "the company" in expanded.lower()
    assert "Acme Corporation" in expanded
    assert "closing date" in expanded.lower()

    # Query with no matching terms
    plain_query = "What happened in the lawsuit?"
    result = CaseContextResolver.expand_references(plain_query, term_map)
    assert result == plain_query  # No changes


def test_format_context_for_prompt(sample_context):
    """format_context_for_prompt includes sections for claims, parties, terms, timeline."""
    formatted = CaseContextResolver.format_context_for_prompt(sample_context)

    # Check all sections are present
    assert "CASE CLAIMS:" in formatted
    assert "Fraud" in formatted
    assert "Breach of Fiduciary Duty" in formatted

    assert "CASE PARTIES:" in formatted
    assert "John Smith" in formatted
    assert "Acme Corporation" in formatted
    assert "plaintiff" in formatted
    assert "defendant" in formatted

    assert "DEFINED TERMS:" in formatted
    assert "the Agreement" in formatted
    assert "Stock Purchase Agreement" in formatted

    assert "KEY TIMELINE:" in formatted
    assert "January 1, 2020" in formatted
    assert "Agreement signed" in formatted
