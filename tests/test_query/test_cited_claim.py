"""Tests for CitedClaim and VerificationJudgment schemas."""

import pytest
from pydantic import ValidationError

from app.query.schemas import CitedClaim


def test_cited_claim_serialization():
    """CitedClaim round-trips through model_dump with all fields present."""
    claim = CitedClaim(
        claim_text="The contract was signed on January 5, 2024.",
        document_id="doc-001",
        filename="contract.pdf",
        page_number=3,
        bates_range="NEXUS-00042",
        excerpt="Signed this 5th day of January 2024",
        grounding_score=0.92,
        verification_status="verified",
    )

    data = claim.model_dump()

    assert data["claim_text"] == "The contract was signed on January 5, 2024."
    assert data["document_id"] == "doc-001"
    assert data["filename"] == "contract.pdf"
    assert data["page_number"] == 3
    assert data["bates_range"] == "NEXUS-00042"
    assert data["excerpt"] == "Signed this 5th day of January 2024"
    assert isinstance(data["grounding_score"], float)
    assert data["grounding_score"] == 0.92
    assert data["verification_status"] == "verified"


def test_cited_claim_validation_bounds():
    """grounding_score must be 0.0-1.0 and excerpt must be <= 500 chars."""
    # grounding_score out of bounds (above 1.0)
    with pytest.raises(ValidationError):
        CitedClaim(
            claim_text="Some claim",
            document_id="doc-001",
            filename="file.pdf",
            excerpt="Short excerpt",
            grounding_score=1.5,
        )

    # grounding_score out of bounds (below 0.0)
    with pytest.raises(ValidationError):
        CitedClaim(
            claim_text="Some claim",
            document_id="doc-001",
            filename="file.pdf",
            excerpt="Short excerpt",
            grounding_score=-0.1,
        )

    # excerpt exceeds max_length=500
    with pytest.raises(ValidationError):
        CitedClaim(
            claim_text="Some claim",
            document_id="doc-001",
            filename="file.pdf",
            excerpt="x" * 501,
            grounding_score=0.5,
        )
