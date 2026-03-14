"""Tests for SPLADEProvider: lazy loading, asymmetric encoding, and output format."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import torch

from app.ingestion.splade_embedder import SPLADEProvider


def _make_mock_output(vocab_size: int = 30522, nonzero_indices: list[int] | None = None) -> MagicMock:
    """Build a mock model output with realistic logits tensor."""
    if nonzero_indices is None:
        nonzero_indices = [10, 50, 200]
    logits = torch.zeros(1, 5, vocab_size)  # (batch, seq_len, vocab)
    for idx in nonzero_indices:
        logits[0, 0, idx] = 2.0  # Will produce log1p(relu(2.0)) ≈ 1.0986
    output = MagicMock()
    output.logits = logits
    return output


def _make_mock_tokenizer() -> MagicMock:
    """Build a mock tokenizer that returns a dict-like object."""
    tokenizer = MagicMock()
    tokenizer.return_value = {
        "input_ids": torch.tensor([[101, 2023, 102]]),
        "attention_mask": torch.tensor([[1, 1, 1]]),
    }
    return tokenizer


def _make_mock_model(output: MagicMock) -> MagicMock:
    """Build a mock masked LM model."""
    model = MagicMock()
    model.return_value = output
    model.eval = MagicMock()
    return model


class TestSPLADEProviderInit:
    """Verify lazy loading behaviour."""

    def test_init_does_not_load_models(self):
        """Models should be None after construction (lazy loading)."""
        provider = SPLADEProvider(doc_model="test/doc", query_model="test/query")
        assert provider._doc_model is None
        assert provider._doc_tokenizer is None
        assert provider._query_model is None
        assert provider._query_tokenizer is None

    @patch("app.ingestion.splade_embedder.AutoModelForMaskedLM.from_pretrained")
    @patch("app.ingestion.splade_embedder.AutoTokenizer.from_pretrained")
    def test_ensure_doc_model_loads_on_first_call(self, mock_tok, mock_model):
        """_ensure_doc_model should load tokenizer + model on first call."""
        mock_tok.return_value = MagicMock()
        mock_model.return_value = MagicMock()

        provider = SPLADEProvider(doc_model="test/doc", query_model="test/query")
        provider._ensure_doc_model()

        mock_tok.assert_called_once_with("test/doc")
        mock_model.assert_called_once_with("test/doc")
        assert provider._doc_tokenizer is not None
        assert provider._doc_model is not None

    @patch("app.ingestion.splade_embedder.AutoModelForMaskedLM.from_pretrained")
    @patch("app.ingestion.splade_embedder.AutoTokenizer.from_pretrained")
    def test_ensure_query_model_loads_on_first_call(self, mock_tok, mock_model):
        """_ensure_query_model should load tokenizer + model on first call."""
        mock_tok.return_value = MagicMock()
        mock_model.return_value = MagicMock()

        provider = SPLADEProvider(doc_model="test/doc", query_model="test/query")
        provider._ensure_query_model()

        mock_tok.assert_called_once_with("test/query")
        mock_model.assert_called_once_with("test/query")
        assert provider._query_tokenizer is not None
        assert provider._query_model is not None


class TestSPLADEProviderEncoding:
    """Verify embedding output format and asymmetric routing."""

    def test_embed_texts_returns_sparse_vectors(self):
        """embed_texts should return list of (indices, values) tuples."""
        provider = SPLADEProvider()
        output = _make_mock_output(nonzero_indices=[10, 50, 200])
        provider._doc_tokenizer = _make_mock_tokenizer()
        provider._doc_model = _make_mock_model(output)

        results = provider.embed_texts(["test document"])

        assert len(results) == 1
        indices, values = results[0]
        assert isinstance(indices, list)
        assert isinstance(values, list)
        assert len(indices) == len(values)
        assert 10 in indices
        assert 50 in indices
        assert 200 in indices

    def test_embed_single_convenience_wrapper(self):
        """embed_single should return a single (indices, values) tuple."""
        provider = SPLADEProvider()
        output = _make_mock_output(nonzero_indices=[5, 100])
        provider._doc_tokenizer = _make_mock_tokenizer()
        provider._doc_model = _make_mock_model(output)

        indices, values = provider.embed_single("test document")

        assert isinstance(indices, list)
        assert isinstance(values, list)
        assert 5 in indices
        assert 100 in indices

    def test_embed_query_sparse_uses_query_model(self):
        """embed_query_sparse should use the query model, not the doc model."""
        provider = SPLADEProvider()
        query_output = _make_mock_output(nonzero_indices=[7, 42])
        provider._query_tokenizer = _make_mock_tokenizer()
        provider._query_model = _make_mock_model(query_output)

        # Set doc model to different output to verify it's NOT used
        doc_output = _make_mock_output(nonzero_indices=[999])
        provider._doc_tokenizer = _make_mock_tokenizer()
        provider._doc_model = _make_mock_model(doc_output)

        indices, values = provider.embed_query_sparse("test query")

        assert 7 in indices
        assert 42 in indices
        assert 999 not in indices
        provider._query_model.assert_called_once()
        provider._doc_model.assert_not_called()

    def test_sparse_vector_format_indices_values(self):
        """Sparse vector indices should be ints, values should be positive floats."""
        provider = SPLADEProvider()
        output = _make_mock_output(nonzero_indices=[3, 15, 77])
        provider._doc_tokenizer = _make_mock_tokenizer()
        provider._doc_model = _make_mock_model(output)

        indices, values = provider.embed_single("test")

        for idx in indices:
            assert isinstance(idx, int)
        for val in values:
            assert isinstance(val, float)
            assert val > 0.0

    def test_max_length_respected(self):
        """Tokenizer should receive the configured max_length."""
        provider = SPLADEProvider(max_length=256)
        output = _make_mock_output(nonzero_indices=[1])
        mock_tokenizer = _make_mock_tokenizer()
        mock_model = _make_mock_model(output)
        provider._doc_tokenizer = mock_tokenizer
        provider._doc_model = mock_model

        provider.embed_single("test")

        call_kwargs = mock_tokenizer.call_args
        assert call_kwargs[1]["max_length"] == 256

    def test_empty_text_produces_valid_output(self):
        """Empty string should still produce a valid (indices, values) tuple."""
        provider = SPLADEProvider()
        # Empty text may still produce some non-zero activations from special tokens
        output = _make_mock_output(nonzero_indices=[101])
        provider._doc_tokenizer = _make_mock_tokenizer()
        provider._doc_model = _make_mock_model(output)

        indices, values = provider.embed_single("")

        assert isinstance(indices, list)
        assert isinstance(values, list)
        assert len(indices) == len(values)

    def test_multiple_texts_batch(self):
        """embed_texts should process each text independently."""
        provider = SPLADEProvider()
        output = _make_mock_output(nonzero_indices=[10, 20])
        provider._doc_tokenizer = _make_mock_tokenizer()
        provider._doc_model = _make_mock_model(output)

        results = provider.embed_texts(["text one", "text two", "text three"])

        assert len(results) == 3
        for indices, values in results:
            assert isinstance(indices, list)
            assert isinstance(values, list)
            assert len(indices) == len(values)
