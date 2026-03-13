"""Tests for the classify_tier heuristic function."""

from app.query.nodes import classify_tier


def testclassify_tier_fast_simple_query():
    """Short factual queries with a question mark should return 'fast'."""
    result = classify_tier("Who is John?")
    assert result == "fast"


def testclassify_tier_standard_moderate_query():
    """Medium-complexity queries without deep markers should return 'standard'."""
    result = classify_tier("What documents mention the acquisition agreement between Company A and Company B")
    assert result == "standard"


def testclassify_tier_deep_analytical_query():
    """Complex queries with analytical markers should return 'deep'."""
    result = classify_tier("Compare the testimony of Smith and Jones regarding the timeline of events")
    assert result == "deep"
