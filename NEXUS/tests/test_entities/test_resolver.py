"""Tests for the entity resolver (fuzzy matching + canonical selection)."""

from __future__ import annotations

import pytest

from app.entities.resolver import EntityMatch, EntityResolver


# ---------------------------------------------------------------------------
# Fuzzy matching tests (8)
# ---------------------------------------------------------------------------

def test_fuzzy_exact_match():
    """Identical names within the same type should always match."""
    resolver = EntityResolver(fuzzy_threshold=85)
    entities = [
        {"name": "Jeffrey Epstein", "type": "person"},
        {"name": "Jeffrey Epstein", "type": "person"},
    ]
    matches = resolver.find_fuzzy_matches(entities)
    # Deduped internally, so identical names = 1 unique → no pairs
    assert len(matches) == 0


def test_fuzzy_close_names():
    """Names differing by one character should match at threshold 85."""
    resolver = EntityResolver(fuzzy_threshold=80)
    entities = [
        {"name": "Jeffrey Epstein", "type": "person"},
        {"name": "Jeffery Epstein", "type": "person"},
    ]
    matches = resolver.find_fuzzy_matches(entities)
    assert len(matches) == 1
    assert matches[0].entity_type == "person"
    assert matches[0].method == "fuzzy"


def test_fuzzy_different_types_no_match():
    """Entities of different types should not be compared."""
    resolver = EntityResolver(fuzzy_threshold=80)
    entities = [
        {"name": "Apple", "type": "organization"},
        {"name": "Apple", "type": "location"},
    ]
    matches = resolver.find_fuzzy_matches(entities)
    assert len(matches) == 0


def test_fuzzy_below_threshold():
    """Names that are very different should not match."""
    resolver = EntityResolver(fuzzy_threshold=85)
    entities = [
        {"name": "John Smith", "type": "person"},
        {"name": "Jane Doe", "type": "person"},
    ]
    matches = resolver.find_fuzzy_matches(entities)
    assert len(matches) == 0


def test_fuzzy_abbreviation():
    """Common abbreviation patterns should match (J. Epstein vs Jeffrey Epstein)."""
    resolver = EntityResolver(fuzzy_threshold=70)  # Lower threshold for abbreviations
    entities = [
        {"name": "Jeffrey Epstein", "type": "person"},
        {"name": "J. Epstein", "type": "person"},
    ]
    matches = resolver.find_fuzzy_matches(entities)
    assert len(matches) == 1


def test_fuzzy_case_insensitive():
    """Fuzzy matching should be case-insensitive."""
    resolver = EntityResolver(fuzzy_threshold=85)
    entities = [
        {"name": "JEFFREY EPSTEIN", "type": "person"},
        {"name": "jeffrey epstein", "type": "person"},
    ]
    matches = resolver.find_fuzzy_matches(entities)
    assert len(matches) == 1


def test_fuzzy_multiple_types():
    """Resolution should run separately for each entity type."""
    resolver = EntityResolver(fuzzy_threshold=80)
    entities = [
        {"name": "New York", "type": "location"},
        {"name": "New Yorke", "type": "location"},
        {"name": "Acme Corporation", "type": "organization"},
        {"name": "Acme Corporations", "type": "organization"},
    ]
    matches = resolver.find_fuzzy_matches(entities)
    assert len(matches) == 2
    types = {m.entity_type for m in matches}
    assert types == {"location", "organization"}


def test_fuzzy_single_entity_no_match():
    """A single entity should produce no matches."""
    resolver = EntityResolver()
    entities = [{"name": "Solo Entity", "type": "person"}]
    matches = resolver.find_fuzzy_matches(entities)
    assert len(matches) == 0


# ---------------------------------------------------------------------------
# Canonical selection tests (built into fuzzy tests above, plus explicit)
# ---------------------------------------------------------------------------

def test_select_canonical_prefers_longer():
    """The longer (more complete) name should be canonical."""
    canonical, alias = EntityResolver.select_canonical(
        "J. Epstein", "Jeffrey Epstein"
    )
    assert canonical == "Jeffrey Epstein"
    assert alias == "J. Epstein"


def test_select_canonical_prefers_proper_case():
    """Proper case should be preferred over all-caps or all-lower."""
    canonical, alias = EntityResolver.select_canonical(
        "JOHN SMITH", "John Smith"
    )
    assert canonical == "John Smith"
    assert alias == "JOHN SMITH"
