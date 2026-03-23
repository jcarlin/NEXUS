"""Cross-encoder reranker using sentence-transformers.

The model is lazy-loaded on first use (~1GB, auto-detects MPS/CUDA/CPU).
Feature-flagged via ``ENABLE_RERANKER`` — when disabled, the DI layer
returns ``None`` and the rerank node falls back to score-based sorting.
"""

from __future__ import annotations

import httpx
import structlog
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

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


class TEIReranker:
    """Reranker via a HuggingFace Text Embeddings Inference server.

    Calls the TEI ``/rerank`` endpoint over HTTP.  Async-only.
    """

    def __init__(self, base_url: str = "http://localhost:8082") -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=120.0)

    @retry(
        retry=retry_if_exception_type((httpx.ConnectError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        reraise=True,
        before_sleep=before_sleep_log(logger, "warning"),  # type: ignore[arg-type]
    )
    async def rerank(
        self,
        query: str,
        results: list[dict],
        *,
        top_n: int = 10,
        text_key: str = "chunk_text",
    ) -> list[dict]:
        """Rerank *results* by relevance to *query* via TEI.

        Returns top *top_n* results sorted by cross-encoder score (descending).
        """
        if not results:
            return []

        texts = [r.get(text_key, "") for r in results]

        response = await self._client.post(
            "/rerank",
            json={"query": query, "texts": texts, "truncate": True},
        )
        response.raise_for_status()
        scored: list[dict] = response.json()

        # TEI returns [{"index": 0, "score": 0.99}, ...] — map back to results
        for item in scored:
            idx = item["index"]
            results[idx]["score"] = float(item["score"])

        ranked = sorted(results, key=lambda r: r["score"], reverse=True)

        logger.debug(
            "reranker.tei.complete",
            base_url=self._base_url,
            count=len(results),
            top_n=top_n,
        )
        return ranked[:top_n]

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()


class InfinityReranker:
    """Reranker via a michaelfeil/infinity server.

    Uses the ``/rerank`` endpoint with ``documents`` field
    (differs from TEI which uses ``texts``).
    """

    def __init__(
        self,
        base_url: str = "http://localhost:7997",
        model: str = "BAAI/bge-reranker-v2-m3",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=120.0)

    @retry(
        retry=retry_if_exception_type((httpx.ConnectError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        reraise=True,
        before_sleep=before_sleep_log(logger, "warning"),  # type: ignore[arg-type]
    )
    async def rerank(
        self,
        query: str,
        results: list[dict],
        *,
        top_n: int = 10,
        text_key: str = "chunk_text",
    ) -> list[dict]:
        """Rerank *results* by relevance to *query* via Infinity.

        Returns top *top_n* results sorted by cross-encoder score (descending).
        """
        if not results:
            return []

        texts = [r.get(text_key, "") for r in results]

        response = await self._client.post(
            "/rerank",
            json={
                "query": query,
                "documents": texts,
                "model": self._model,
            },
        )
        response.raise_for_status()
        data = response.json()

        # Infinity returns {"results": [{"index": 0, "relevance_score": 0.99}, ...]}
        for item in data["results"]:
            idx = item["index"]
            results[idx]["score"] = float(item["relevance_score"])

        ranked = sorted(results, key=lambda r: r["score"], reverse=True)

        logger.debug(
            "reranker.infinity.complete",
            base_url=self._base_url,
            count=len(results),
            top_n=top_n,
        )
        return ranked[:top_n]

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()
