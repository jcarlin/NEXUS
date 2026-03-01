"""Tests for the VisualEmbedder (ColQwen2.5 multi-vector wrapper)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import torch

from app.ingestion.visual_embedder import VisualEmbedder

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def embedder():
    """Return a VisualEmbedder without loading the model."""
    return VisualEmbedder(model_name="vidore/colqwen2.5-v0.2", device="cpu")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_lazy_loading(embedder):
    """Model should be None after init and only loaded on first call."""
    assert embedder._model is None
    assert embedder._processor is None


@patch("app.ingestion.visual_embedder.ColQwen2_5_Processor", create=True)
@patch("app.ingestion.visual_embedder.ColQwen2_5", create=True)
def test_embed_images_dimensions(mock_model_cls, mock_processor_cls, embedder):
    """embed_images should return list[list[list[float]]] with 128d vectors."""
    # Mock model and processor
    mock_model = MagicMock()
    mock_model.device = torch.device("cpu")

    # Simulate model output: 2 images, 4 patches each, 128d
    mock_output = torch.randn(2, 4, 128, dtype=torch.float32)
    mock_model.__call__ = MagicMock(return_value=mock_output)
    mock_model.return_value = mock_output

    mock_processor = MagicMock()
    mock_batch = MagicMock()
    mock_batch.to.return_value = mock_batch
    mock_processor.process_images.return_value = mock_batch

    # Patch the lazy load
    with patch.object(embedder, "_load_model"):
        embedder._model = mock_model
        embedder._processor = mock_processor

        fake_images = [MagicMock(), MagicMock()]  # 2 PIL images
        result = embedder.embed_images(fake_images)

    assert len(result) == 2  # 2 images
    assert len(result[0]) == 4  # 4 patches
    assert len(result[0][0]) == 128  # 128d


@patch("app.ingestion.visual_embedder.ColQwen2_5_Processor", create=True)
@patch("app.ingestion.visual_embedder.ColQwen2_5", create=True)
def test_embed_query_dimensions(mock_model_cls, mock_processor_cls, embedder):
    """embed_query should return list[list[float]] with 128d vectors."""
    mock_model = MagicMock()
    mock_model.device = torch.device("cpu")

    # Simulate model output: 1 query, 8 tokens, 128d
    mock_output = torch.randn(1, 8, 128, dtype=torch.float32)
    mock_model.__call__ = MagicMock(return_value=mock_output)
    mock_model.return_value = mock_output

    mock_processor = MagicMock()
    mock_batch = MagicMock()
    mock_batch.to.return_value = mock_batch
    mock_processor.process_queries.return_value = mock_batch

    embedder._model = mock_model
    embedder._processor = mock_processor

    result = embedder.embed_query("What tables are in this document?")

    assert len(result) == 8  # 8 query tokens
    assert len(result[0]) == 128  # 128d


def test_compute_max_sim():
    """MaxSim should correctly compute mean of max cosine similarities."""
    # Query: 2 tokens, 4d
    query = [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]]
    # Doc: 3 patches, 4d
    doc = [[1.0, 0.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0], [0.0, 1.0, 0.0, 0.0]]

    score = VisualEmbedder.compute_max_sim(query, doc)

    # Token 0 max sim = cos(q0, d0) = 1.0
    # Token 1 max sim = cos(q1, d2) = 1.0
    # Mean = (1.0 + 1.0) / 2 = 1.0
    assert abs(score - 1.0) < 1e-5


def test_compute_max_sim_partial_match():
    """MaxSim with partial matches produces intermediate scores."""
    # Query: 2 tokens, 4d
    query = [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]]
    # Doc: 1 patch that only matches first query token
    doc = [[1.0, 0.0, 0.0, 0.0]]

    score = VisualEmbedder.compute_max_sim(query, doc)

    # Token 0 max sim = 1.0 (exact match)
    # Token 1 max sim = 0.0 (orthogonal)
    # Mean = 0.5
    assert abs(score - 0.5) < 1e-5


# ---------------------------------------------------------------------------
# _is_visually_complex tests
# ---------------------------------------------------------------------------


def test_is_visually_complex_tables():
    """Pages with tables should be flagged as visually complex."""
    from app.ingestion.tasks import _is_visually_complex

    assert _is_visually_complex("Some text content here", "document.pdf", has_tables=True) is True


def test_is_visually_complex_low_text():
    """Pages with very little text should be flagged as visually complex."""
    from app.ingestion.tasks import _is_visually_complex

    assert _is_visually_complex("short", "document.pdf") is True


def test_is_visually_complex_text_heavy():
    """Text-heavy pages without tables should not be flagged."""
    from app.ingestion.tasks import _is_visually_complex

    long_text = "This is a substantial paragraph of legal text. " * 10
    assert _is_visually_complex(long_text, "document.pdf") is False


def test_is_visually_complex_pptx():
    """Presentation files should always be flagged as visually complex."""
    from app.ingestion.tasks import _is_visually_complex

    long_text = "This is a substantial paragraph of text. " * 10
    assert _is_visually_complex(long_text, "slides.pptx") is True


def test_is_visually_complex_xlsx():
    """Spreadsheet files should always be flagged as visually complex."""
    from app.ingestion.tasks import _is_visually_complex

    long_text = "This is a substantial paragraph of text. " * 10
    assert _is_visually_complex(long_text, "data.xlsx") is True
