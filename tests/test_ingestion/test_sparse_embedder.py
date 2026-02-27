"""Tests for SparseEmbedder: lazy loading and output format."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.ingestion.sparse_embedder import SparseEmbedder


def test_lazy_loads_model():
    """Model should be None after init, loaded only on first call."""
    embedder = SparseEmbedder(model_name="test-model")
    assert embedder._model is None


def test_embed_texts_returns_indices_values():
    """embed_texts should return list of (indices, values) tuples."""
    embedder = SparseEmbedder(model_name="test-model")

    # Mock the fastembed model
    mock_result = MagicMock()
    mock_result.indices.tolist.return_value = [0, 3, 7]
    mock_result.values.tolist.return_value = [0.5, 0.8, 0.3]

    mock_model = MagicMock()
    mock_model.embed.return_value = [mock_result]

    with patch("app.ingestion.sparse_embedder.SparseEmbedder._load_model", return_value=mock_model):
        embedder._model = mock_model
        results = embedder.embed_texts(["hello world"])

    assert len(results) == 1
    indices, values = results[0]
    assert indices == [0, 3, 7]
    assert values == [0.5, 0.8, 0.3]
