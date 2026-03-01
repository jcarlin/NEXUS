"""Tests for the _parse_claims helper."""

from app.query.nodes import _parse_claims


def test_parse_claims_from_json():
    """_parse_claims extracts claims from clean JSON and JSON embedded in text."""
    # Clean JSON array
    clean = '[{"claim_text": "Contract signed", "filename": "a.pdf", "page_number": 1}]'
    result = _parse_claims(clean)
    assert len(result) == 1
    assert result[0]["claim_text"] == "Contract signed"

    # JSON embedded in surrounding prose
    embedded = (
        "Here are the claims I extracted:\n"
        '[{"claim_text": "First claim", "filename": "b.pdf", "page_number": 2}, '
        '{"claim_text": "Second claim", "filename": "c.pdf", "page_number": 5}]\n'
        "Let me know if you need more."
    )
    result = _parse_claims(embedded)
    assert len(result) == 2
    assert result[0]["claim_text"] == "First claim"
    assert result[1]["claim_text"] == "Second claim"

    # No JSON at all should return empty list
    assert _parse_claims("No JSON here at all.") == []
