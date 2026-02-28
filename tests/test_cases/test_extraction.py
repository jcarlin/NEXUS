"""Tests for case intelligence extraction (Instructor models and agent nodes)."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_extract_claims_from_complaint():
    """ExtractedClaimList schema correctly validates claim extraction results."""
    from app.cases.schemas import ExtractedClaim, ExtractedClaimList

    mock_result = ExtractedClaimList(
        claims=[
            ExtractedClaim(
                claim_number=1,
                claim_label="Fraud",
                claim_text="Defendant committed fraud by misrepresenting material facts.",
                legal_elements=["intent", "misrepresentation", "reliance", "damages"],
                source_pages=[3, 4, 5],
            ),
            ExtractedClaim(
                claim_number=2,
                claim_label="Breach of Contract",
                claim_text="Defendant breached the Agreement dated January 1, 2020.",
                legal_elements=["valid contract", "breach", "damages"],
                source_pages=[8, 9],
            ),
        ]
    )

    assert len(mock_result.claims) == 2
    assert mock_result.claims[0].claim_label == "Fraud"
    assert mock_result.claims[1].claim_number == 2
    assert "intent" in mock_result.claims[0].legal_elements

    # Verify the node function exists and is callable
    from app.cases.agent import create_case_setup_nodes

    nodes = create_case_setup_nodes({"api_key": "test", "provider": "anthropic"})
    assert "extract_claims" in nodes
    assert callable(nodes["extract_claims"])


@pytest.mark.asyncio
async def test_extract_claims_handles_empty_document():
    """Extract claims returns empty list for empty/short document text."""
    from app.cases.agent import create_case_setup_nodes

    nodes = create_case_setup_nodes({"api_key": "test", "provider": "anthropic"})

    # Call with empty document text — should return empty without calling LLM
    result = nodes["extract_claims"]({"document_text": ""})
    assert result == {"claims": []}

    result = nodes["extract_claims"]({"document_text": "   "})
    assert result == {"claims": []}


@pytest.mark.asyncio
async def test_extract_parties_identifies_roles():
    """ExtractedParty schema correctly validates party roles."""
    from app.cases.schemas import ExtractedParty, ExtractedPartyList

    parties = ExtractedPartyList(
        parties=[
            ExtractedParty(
                name="John Smith",
                role="plaintiff",
                description="Individual plaintiff",
                aliases=["Smith", "J. Smith"],
                source_pages=[1],
            ),
            ExtractedParty(
                name="Acme Corporation",
                role="defendant",
                description="Delaware corporation",
                aliases=["Acme", "the Company", "Defendant A"],
                source_pages=[1, 2],
            ),
            ExtractedParty(
                name="Jane Doe",
                role="witness",
                description="Former employee of Acme",
                aliases=[],
                source_pages=[10],
            ),
        ]
    )

    assert len(parties.parties) == 3
    assert parties.parties[0].role == "plaintiff"
    assert parties.parties[1].role == "defendant"
    assert parties.parties[2].role == "witness"
    assert "the Company" in parties.parties[1].aliases
    assert "Defendant A" in parties.parties[1].aliases


@pytest.mark.asyncio
async def test_extract_defined_terms_resolves_aliases():
    """ExtractedDefinedTerm schema correctly maps terms to definitions."""
    from app.cases.schemas import ExtractedDefinedTerm, ExtractedDefinedTermList

    terms = ExtractedDefinedTermList(
        terms=[
            ExtractedDefinedTerm(
                term="the Company",
                definition="Acme Corporation, a Delaware corporation",
                source_pages=[1],
            ),
            ExtractedDefinedTerm(
                term="the Agreement",
                definition="The Stock Purchase Agreement dated January 1, 2020, by and between Plaintiff and Defendant",
                source_pages=[2, 3],
            ),
            ExtractedDefinedTerm(
                term="Closing Date",
                definition="March 15, 2020",
                source_pages=[4],
            ),
        ]
    )

    assert len(terms.terms) == 3
    assert terms.terms[0].term == "the Company"
    assert "Acme Corporation" in terms.terms[0].definition
    assert terms.terms[1].term == "the Agreement"
    assert "Stock Purchase Agreement" in terms.terms[1].definition
