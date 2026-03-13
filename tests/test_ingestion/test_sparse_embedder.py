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


# ---------------------------------------------------------------------------
# BGEM3SparseAdapter
# ---------------------------------------------------------------------------


def test_bgem3_sparse_adapter_delegates():
    """BGEM3SparseAdapter.embed_texts should delegate to provider.embed_sparse_sync."""
    from app.ingestion.sparse_embedder import BGEM3SparseAdapter

    mock_provider = MagicMock()
    mock_provider.embed_sparse_sync.return_value = [([1, 2, 3], [0.5, 0.8, 0.3])]

    adapter = BGEM3SparseAdapter(mock_provider)
    result = adapter.embed_texts(["hello world"])

    mock_provider.embed_sparse_sync.assert_called_once_with(["hello world"])
    assert len(result) == 1
    assert result[0] == ([1, 2, 3], [0.5, 0.8, 0.3])


def test_bgem3_sparse_adapter_embed_single():
    """BGEM3SparseAdapter.embed_single should return a single (indices, values) tuple."""
    from app.ingestion.sparse_embedder import BGEM3SparseAdapter

    mock_provider = MagicMock()
    mock_provider.embed_sparse_sync.return_value = [([10, 20], [0.1, 0.9])]

    adapter = BGEM3SparseAdapter(mock_provider)
    indices, values = adapter.embed_single("test text")

    assert indices == [10, 20]
    assert values == [0.1, 0.9]
