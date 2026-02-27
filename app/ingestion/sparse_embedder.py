"""Sparse text embedding via FastEmbed (BM42).

Lazy-loads the model on first use, following the same pattern as
``Reranker`` and ``EntityExtractor``. Synchronous — called via
``asyncio.run()`` in Celery tasks or directly in sync contexts.

Feature-flagged via ``ENABLE_SPARSE_EMBEDDINGS``.
"""

from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)


class SparseEmbedder:
    """BM42 sparse embedding generator. Model loaded lazily on first call."""

    def __init__(self, model_name: str = "Qdrant/bm42-all-minilm-l6-v2-attentions") -> None:
        self._model_name = model_name
        self._model = None

    def _load_model(self):
        """Load the SparseTextEmbedding model into memory (once)."""
        if self._model is None:
            from fastembed import SparseTextEmbedding

            logger.info("sparse_embedder.loading", model=self._model_name)
            self._model = SparseTextEmbedding(model_name=self._model_name)
            logger.info("sparse_embedder.loaded")
        return self._model

    def embed_texts(self, texts: list[str]) -> list[tuple[list[int], list[float]]]:
        """Generate sparse embeddings for a batch of texts.

        Returns:
            List of (indices, values) tuples — one per input text.
        """
        model = self._load_model()
        results = list(model.embed(texts))
        return [(r.indices.tolist(), r.values.tolist()) for r in results]

    def embed_single(self, text: str) -> tuple[list[int], list[float]]:
        """Convenience wrapper for a single text."""
        return self.embed_texts([text])[0]
