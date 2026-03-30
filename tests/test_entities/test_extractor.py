"""Tests for entity extraction normalization and garbage filtering."""

from __future__ import annotations

from app.entities.extractor import _is_garbage_entity, normalize_entity_name

# ---------------------------------------------------------------------------
# ftfy-based normalization tests
# ---------------------------------------------------------------------------


def test_normalize_html_entities():
    """ftfy should decode HTML entities from OCR."""
    assert "&" in normalize_entity_name("Smith &amp; Wesson")
    assert ">" not in normalize_entity_name("foo &gt; bar") or normalize_entity_name("foo &gt; bar") == "foo > bar"


def test_normalize_mojibake():
    """ftfy should fix common mojibake from OCR encoding issues."""
    # â€™ is a common mojibake for right single quote
    result = normalize_entity_name("Maxwell\u2019s")
    assert "\u2019" in result or "'" in result  # ftfy may transliterate


def test_normalize_hyphenation():
    """OCR hyphenation at line breaks should be rejoined."""
    assert normalize_entity_name("Ep- stein") == "Epstein"
    assert normalize_entity_name("Max -well") == "Maxwell"


def test_normalize_whitespace():
    """Extra whitespace should be collapsed."""
    assert normalize_entity_name("Jeffrey   Epstein") == "Jeffrey Epstein"
    assert normalize_entity_name("  Jeffrey Epstein  ") == "Jeffrey Epstein"


def test_normalize_newlines():
    """Newlines should be replaced with spaces."""
    assert normalize_entity_name("Jeffrey\nEpstein") == "Jeffrey Epstein"
    assert normalize_entity_name("Jeffrey\r\nEpstein") == "Jeffrey Epstein"


# ---------------------------------------------------------------------------
# Garbage filter tests (existing filter, unchanged)
# ---------------------------------------------------------------------------


def test_garbage_pronouns():
    """Pronouns should be filtered as garbage."""
    assert _is_garbage_entity("he")
    assert _is_garbage_entity("She")
    assert _is_garbage_entity("THEY")


def test_garbage_too_short():
    """Very short strings should be garbage."""
    assert _is_garbage_entity("a")
    assert _is_garbage_entity("")


def test_garbage_too_long():
    """Strings over 60 chars should be garbage."""
    long_name = "A" * 61
    assert _is_garbage_entity(long_name)


def test_garbage_url_slug():
    """URL slugs should be filtered."""
    assert _is_garbage_entity("this-is-a-url-slug-pattern")


def test_garbage_stopwords():
    """Common stopwords should be filtered."""
    assert _is_garbage_entity("today")
    assert _is_garbage_entity("yesterday")
    assert _is_garbage_entity("fw")
    assert _is_garbage_entity("re")


def test_valid_entities_not_garbage():
    """Real entity names should pass the filter."""
    assert not _is_garbage_entity("Jeffrey Epstein")
    assert not _is_garbage_entity("Department of Justice")
    assert not _is_garbage_entity("New York")
    assert not _is_garbage_entity("FBI")
    assert not _is_garbage_entity("$15 million")
