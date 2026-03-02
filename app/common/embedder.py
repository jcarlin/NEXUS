"""Embedding provider abstraction layer.

Decouples the embedding pipeline from any single vendor (OpenAI, local models)
so that privileged legal documents can be processed locally without sending
content to external APIs.

Usage::

    from app.common.embedder import EmbeddingProvider, OpenAIEmbeddingProvider

    provider: EmbeddingProvider = OpenAIEmbeddingProvider(api_key="...", model="text-embedding-3-large")
    vectors = await provider.embed_texts(["chunk 1", "chunk 2"])
    query_vec = await provider.embed_query("Who is the defendant?")

Privilege compliance: ``OpenAIEmbeddingProvider`` audit-logs every external
API call with a SHA-256 hash of the input data.  ``LocalEmbeddingProvider``
runs entirely on-device — no data leaves the machine.
"""

from __future__ import annotations

import asyncio
import hashlib
from typing import Protocol, runtime_checkable

import httpx
import structlog
from openai import APIConnectionError, APITimeoutError, AsyncOpenAI, RateLimitError
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Interface for dense text embedding providers."""

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts.

        Returns a list of embedding vectors in the same order as *texts*.
        Raises ``ValueError`` if *texts* is empty.
        """
        ...

    async def embed_query(self, text: str) -> list[float]:
        """Embed a single query string.

        Returns one embedding vector.
        """
        ...


# ---------------------------------------------------------------------------
# OpenAI provider
# ---------------------------------------------------------------------------


class OpenAIEmbeddingProvider:
    """Dense embeddings via the OpenAI API (e.g. ``text-embedding-3-large``).

    Batches large inputs and retries transient failures with exponential
    backoff.  Every API call is audit-logged with a SHA-256 hash of the
    concatenated input texts for privilege compliance verification.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "text-embedding-3-large",
        dimensions: int = 1024,
        batch_size: int = 64,
    ) -> None:
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model
        self._dimensions = dimensions
        self.batch_size = batch_size

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of texts, automatically batching if necessary."""
        if not texts:
            raise ValueError("Cannot embed an empty list of texts.")

        all_embeddings: list[list[float]] = []

        for batch_start in range(0, len(texts), self.batch_size):
            batch = texts[batch_start : batch_start + self.batch_size]
            batch_embeddings = await self._embed_batch(batch)
            all_embeddings.extend(batch_embeddings)

            logger.info(
                "embedder.batch_complete",
                batch_start=batch_start,
                batch_size=len(batch),
                total_embedded=len(all_embeddings),
                total_requested=len(texts),
            )

        return all_embeddings

    async def embed_query(self, text: str) -> list[float]:
        """Embed a single query string."""
        results = await self.embed_texts([text])
        return results[0]

    # -- internal ----------------------------------------------------------

    @retry(
        retry=retry_if_exception_type((APIConnectionError, APITimeoutError, RateLimitError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        reraise=True,
        before_sleep=before_sleep_log(logger, "warning"),  # type: ignore[arg-type]
    )
    async def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Call the OpenAI embeddings endpoint for a single batch."""
        # Audit log: hash of input data for privilege compliance
        text_hash = hashlib.sha256("\n".join(texts).encode("utf-8")).hexdigest()[:16]
        logger.info(
            "embedder.external_api_call",
            provider="openai",
            model=self._model,
            text_count=len(texts),
            text_hash=text_hash,
        )

        response = await self._client.embeddings.create(
            model=self._model,
            input=texts,
            dimensions=self._dimensions,
        )

        sorted_data = sorted(response.data, key=lambda item: item.index)
        return [item.embedding for item in sorted_data]


# ---------------------------------------------------------------------------
# Local provider (sentence-transformers)
# ---------------------------------------------------------------------------


class LocalEmbeddingProvider:
    """Dense embeddings via a local sentence-transformers model.

    The model is lazy-loaded on first use (follows the Reranker pattern).
    Inference runs synchronously on CPU/GPU/MPS and is wrapped in
    ``asyncio.to_thread()`` to avoid blocking the event loop.

    No data leaves the machine — safe for privileged documents.
    """

    def __init__(
        self,
        model_name: str = "BAAI/bge-large-en-v1.5",
        dimensions: int = 1024,
    ) -> None:
        self._model_name = model_name
        self._dimensions = dimensions
        self._model = None

    def _load_model(self):
        """Load the SentenceTransformer model into memory (once)."""
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            logger.info("embedder.local.loading", model=self._model_name)
            self._model = SentenceTransformer(self._model_name)
            logger.info("embedder.local.loaded")
        return self._model

    def _encode_sync(self, texts: list[str]) -> list[list[float]]:
        """Synchronous encode — called via ``asyncio.to_thread()``."""
        model = self._load_model()
        embeddings = model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        # Truncate to requested dimensions if model produces more
        result = [row[: self._dimensions].tolist() for row in embeddings]
        return result

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts using the local model."""
        if not texts:
            raise ValueError("Cannot embed an empty list of texts.")

        result = await asyncio.to_thread(self._encode_sync, texts)

        logger.info(
            "embedder.batch_complete",
            provider="local",
            model=self._model_name,
            count=len(texts),
        )
        return result

    async def embed_query(self, text: str) -> list[float]:
        """Embed a single query string."""
        results = await self.embed_texts([text])
        return results[0]


# ---------------------------------------------------------------------------
# TEI provider (HuggingFace Text Embeddings Inference)
# ---------------------------------------------------------------------------


class TEIEmbeddingProvider:
    """Dense embeddings via a HuggingFace Text Embeddings Inference server.

    Calls the TEI ``/embed`` endpoint over HTTP.  No data leaves the
    local network — safe for privileged documents.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8081",
        dimensions: int = 1024,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._dimensions = dimensions
        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=120.0)

    @retry(
        retry=retry_if_exception_type((httpx.ConnectError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        reraise=True,
        before_sleep=before_sleep_log(logger, "warning"),  # type: ignore[arg-type]
    )
    async def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Call the TEI /embed endpoint for a batch of texts."""
        response = await self._client.post(
            "/embed",
            json={"inputs": texts, "truncate": True},
        )
        response.raise_for_status()
        embeddings: list[list[float]] = response.json()

        # Truncate to requested dimensions if model produces more
        return [vec[: self._dimensions] for vec in embeddings]

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts via the TEI server."""
        if not texts:
            raise ValueError("Cannot embed an empty list of texts.")

        result = await self._embed_batch(texts)

        logger.info(
            "embedder.batch_complete",
            provider="tei",
            base_url=self._base_url,
            count=len(texts),
        )
        return result

    async def embed_query(self, text: str) -> list[float]:
        """Embed a single query string."""
        results = await self.embed_texts([text])
        return results[0]

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()
