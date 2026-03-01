"""Tests for the coreference resolution module (M11).

The CoreferenceResolver wraps spaCy + coreferee. Since loading the full
model is expensive and requires `en_core_web_lg` to be installed, we
mock the spaCy pipeline for unit testing.
"""

from __future__ import annotations

from unittest.mock import MagicMock


def test_coreference_resolution_pronoun_anaphora():
    """CoreferenceResolver.resolve() should replace pronouns with referents."""
    from app.entities.coreference import CoreferenceResolver

    resolver = CoreferenceResolver(model_name="en_core_web_lg")

    # Mock the spaCy NLP pipeline
    mock_nlp = MagicMock()

    # Create mock tokens
    def make_token(text, pos, ws=" "):
        tok = MagicMock()
        tok.text = text
        tok.pos_ = pos
        tok.whitespace_ = ws
        tok.text_with_ws = text + ws
        return tok

    tokens = [
        make_token("John", "PROPN"),
        make_token("went", "VERB"),
        make_token("to", "ADP"),
        make_token("the", "DET"),
        make_token("store", "NOUN"),
        make_token(".", "PUNCT", ""),
        make_token(" ", "SPACE"),
        make_token("He", "PRON"),
        make_token("bought", "VERB"),
        make_token("milk", "NOUN"),
        make_token(".", "PUNCT", ""),
    ]

    mock_doc = MagicMock()
    mock_doc.__iter__ = lambda self: iter(tokens)
    mock_doc.__len__ = lambda self: len(tokens)
    mock_doc.__getitem__ = lambda self, idx: tokens[idx]

    # Mock coreferee chain: "He" (token 7) -> "John" (token 0)
    mock_mention_john = MagicMock()
    mock_mention_john.token_indexes = [0]

    mock_mention_he = MagicMock()
    mock_mention_he.token_indexes = [7]

    mock_chain = MagicMock()
    mock_chain.__iter__ = lambda self: iter([mock_mention_john, mock_mention_he])

    mock_coref_chains = MagicMock()
    mock_coref_chains.__iter__ = lambda self: iter([mock_chain])
    mock_coref_chains.__len__ = lambda self: 1

    mock_doc._.coref_chains = mock_coref_chains

    mock_nlp.return_value = mock_doc

    # Inject mock
    resolver._nlp = mock_nlp

    result = resolver.resolve("John went to the store. He bought milk.")

    # "He" should be replaced with "John"
    assert "John" in result
    # The pronoun "He" should be gone
    assert result.count("John") >= 2 or "He" not in result
