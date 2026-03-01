"""Tests for the _classify_tier heuristic function."""

from app.query.nodes import _classify_tier


def test_classify_tier_fast_simple_query():
    """Short factual queries with a question mark should return 'fast'."""
    result = _classify_tier("Who is John?")
    assert result == "fast"


def test_classify_tier_standard_moderate_query():
    """Medium-complexity queries without deep markers should return 'standard'."""
    result = _classify_tier("What documents mention the acquisition agreement between Company A and Company B")
    assert result == "standard"


def test_classify_tier_deep_analytical_query():
    """Complex queries with analytical markers should return 'deep'."""
    result = _classify_tier("Compare the testimony of Smith and Jones regarding the timeline of events")
    assert result == "deep"
