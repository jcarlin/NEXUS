"""Cross-encoder reranker using sentence-transformers.

The model is lazy-loaded on first use (~1GB, auto-detects MPS/CUDA/CPU).
Feature-flagged via ``ENABLE_RERANKER`` — when disabled, the DI layer
returns ``None`` and the rerank node falls back to score-based sorting.
"""

from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)


class Reranker:
    """Cross-encoder reranker.  Model loaded lazily on first call.

    Usage::

        reranker = Reranker()                    # no I/O yet
        ranked = reranker.rerank(query, results)  # loads model on first call
    """

    def __init__(self, model_name: str = "BAAI/bge-reranker-v2-m3") -> None:
        self._model_name = model_name
        self._model = None  # Lazy load — avoids heavy hit at import time

    def _load_model(self):
        """Load the CrossEncoder model into memory (once)."""
        if self._model is None:
            from sentence_transformers import CrossEncoder

            logger.info("reranker.loading", model=self._model_name)
            self._model = CrossEncoder(self._model_name)
            logger.info("reranker.loaded")
        return self._model

    def rerank(
        self,
        query: str,
        results: list[dict],
        *,
        top_n: int = 10,
        text_key: str = "chunk_text",
    ) -> list[dict]:
        """Rerank *results* by cross-encoder relevance to *query*.

        Args:
            query: The user query.
            results: List of result dicts from retrieval.
            top_n: Maximum number of results to return.
            text_key: Key in each result dict containing the passage text.

        Returns:
            Top *top_n* results sorted by cross-encoder score (descending).
        """
        if not results:
            return []

        model = self._load_model()

        pairs = [[query, r.get(text_key, "")] for r in results]
        scores = model.predict(pairs)

        for result, score in zip(results, scores):
            result["score"] = float(score)

        ranked = sorted(results, key=lambda r: r["score"], reverse=True)
        return ranked[:top_n]
