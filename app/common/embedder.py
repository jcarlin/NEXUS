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

        from app.common.metrics import EMBEDDING_CALLS_TOTAL, EMBEDDING_DURATION, track_duration

        all_embeddings: list[list[float]] = []

        with track_duration(EMBEDDING_DURATION, provider="openai"):
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

        EMBEDDING_CALLS_TOTAL.labels(provider="openai").inc()
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
        before_sleep=before_sleep_log(logger, 30),  # logging.WARNING
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

        from app.common.metrics import EMBEDDING_CALLS_TOTAL, EMBEDDING_DURATION, track_duration

        with track_duration(EMBEDDING_DURATION, provider="local"):
            result = await asyncio.to_thread(self._encode_sync, texts)

        EMBEDDING_CALLS_TOTAL.labels(provider="local").inc()
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
# Gemini provider (Google GenAI)
# ---------------------------------------------------------------------------


class GeminiEmbeddingProvider:
    """Dense embeddings via the Google GenAI API (e.g. ``gemini-embedding-exp-03-07``).

    Batches large inputs and retries transient failures with exponential
    backoff.  Every API call is audit-logged with a SHA-256 hash of the
    concatenated input texts for privilege compliance verification.

    The ``google.genai`` client is synchronous, so calls are wrapped in
    ``asyncio.to_thread()`` to avoid blocking the event loop.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-embedding-exp-03-07",
        dimensions: int = 1024,
        batch_size: int = 64,
    ) -> None:
        from google import genai

        self._client = genai.Client(api_key=api_key)
        self._model = model
        self._dimensions = dimensions
        self.batch_size = batch_size

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of texts, automatically batching if necessary."""
        if not texts:
            raise ValueError("Cannot embed an empty list of texts.")

        from app.common.metrics import EMBEDDING_CALLS_TOTAL, EMBEDDING_DURATION, track_duration

        all_embeddings: list[list[float]] = []

        with track_duration(EMBEDDING_DURATION, provider="gemini"):
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

        EMBEDDING_CALLS_TOTAL.labels(provider="gemini").inc()
        return all_embeddings

    async def embed_query(self, text: str) -> list[float]:
        """Embed a single query string."""
        results = await self.embed_texts([text])
        return results[0]

    # -- internal ----------------------------------------------------------

    @retry(
        retry=retry_if_exception_type((ConnectionError, TimeoutError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        reraise=True,
        before_sleep=before_sleep_log(logger, 30),  # logging.WARNING
    )
    async def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Call the Google GenAI embeddings endpoint for a single batch."""
        # Audit log: hash of input data for privilege compliance
        text_hash = hashlib.sha256("\n".join(texts).encode("utf-8")).hexdigest()[:16]
        logger.info(
            "embedder.external_api_call",
            provider="gemini",
            model=self._model,
            text_count=len(texts),
            text_hash=text_hash,
        )

        result = await asyncio.to_thread(
            self._client.models.embed_content,
            model=self._model,
            contents=texts,
            config={"output_dimensionality": self._dimensions},
        )

        return [embedding.values for embedding in result.embeddings]


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
        before_sleep=before_sleep_log(logger, 30),  # logging.WARNING
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

        from app.common.metrics import EMBEDDING_CALLS_TOTAL, EMBEDDING_DURATION, track_duration

        with track_duration(EMBEDDING_DURATION, provider="tei"):
            result = await self._embed_batch(texts)

        EMBEDDING_CALLS_TOTAL.labels(provider="tei").inc()
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


# ---------------------------------------------------------------------------
# Infinity provider (OpenAI-compatible /embeddings endpoint)
# ---------------------------------------------------------------------------


class InfinityEmbeddingProvider:
    """Dense embeddings via a michaelfeil/infinity server.

    Uses the OpenAI-compatible ``/embeddings`` endpoint.
    Supports co-hosted models (embedding + reranker on one GPU).
    """

    def __init__(
        self,
        base_url: str = "http://localhost:7997",
        model: str = "BAAI/bge-m3",
        dimensions: int = 1024,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._dimensions = dimensions
        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=120.0)

    @retry(
        retry=retry_if_exception_type((httpx.ConnectError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        reraise=True,
        before_sleep=before_sleep_log(logger, 30),
    )
    async def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        response = await self._client.post(
            "/embeddings",
            json={"input": texts, "model": self._model},
        )
        response.raise_for_status()
        data = response.json()
        embeddings = [item["embedding"] for item in data["data"]]
        return [vec[: self._dimensions] for vec in embeddings]

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            raise ValueError("Cannot embed an empty list of texts.")

        from app.common.metrics import EMBEDDING_CALLS_TOTAL, EMBEDDING_DURATION, track_duration

        with track_duration(EMBEDDING_DURATION, provider="infinity"):
            result = await self._embed_batch(texts)

        EMBEDDING_CALLS_TOTAL.labels(provider="infinity").inc()
        logger.info(
            "embedder.batch_complete",
            provider="infinity",
            base_url=self._base_url,
            count=len(texts),
        )
        return result

    async def embed_query(self, text: str) -> list[float]:
        results = await self.embed_texts([text])
        return results[0]

    async def close(self) -> None:
        await self._client.aclose()


# ---------------------------------------------------------------------------
# Ollama provider (native /api/embed endpoint)
# ---------------------------------------------------------------------------


class OllamaEmbeddingProvider:
    """Dense embeddings via a local Ollama server.

    Calls the native ``/api/embed`` endpoint (not the OpenAI-compatible API).
    No data leaves the machine — safe for privileged documents.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "nomic-embed-text",
        dimensions: int = 768,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._dimensions = dimensions
        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=120.0)

    @retry(
        retry=retry_if_exception_type((httpx.ConnectError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        reraise=True,
        before_sleep=before_sleep_log(logger, 30),  # logging.WARNING
    )
    async def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Call the Ollama /api/embed endpoint for a batch of texts."""
        response = await self._client.post(
            "/api/embed",
            json={"model": self._model, "input": texts},
        )
        response.raise_for_status()
        data = response.json()
        embeddings: list[list[float]] = data["embeddings"]

        # Truncate to requested dimensions if model produces more
        return [vec[: self._dimensions] for vec in embeddings]

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts via the Ollama server."""
        if not texts:
            raise ValueError("Cannot embed an empty list of texts.")

        from app.common.metrics import EMBEDDING_CALLS_TOTAL, EMBEDDING_DURATION, track_duration

        with track_duration(EMBEDDING_DURATION, provider="ollama"):
            result = await self._embed_batch(texts)

        EMBEDDING_CALLS_TOTAL.labels(provider="ollama").inc()
        logger.info(
            "embedder.batch_complete",
            provider="ollama",
            model=self._model,
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


# ---------------------------------------------------------------------------
# BGE-M3 provider (unified dense + sparse in single forward pass)
# ---------------------------------------------------------------------------


class BGEM3Provider:
    """Unified dense + sparse embeddings via BGE-M3 (``BAAI/bge-m3``).

    A single forward pass produces dense (1024-d), sparse (lexical weights),
    and optionally ColBERT vectors.  The model is lazy-loaded on first use
    and inference runs synchronously, wrapped in ``asyncio.to_thread()``.

    No data leaves the machine — safe for privileged documents.
    """

    def __init__(
        self,
        model_name: str = "BAAI/bge-m3",
        max_length: int = 8192,
        batch_size: int = 12,
        use_fp16: bool = True,
    ) -> None:
        self._model_name = model_name
        self._max_length = max_length
        self._batch_size = batch_size
        self._use_fp16 = use_fp16
        self._model = None

    def _load_model(self):
        """Load the BGEM3FlagModel into memory (once)."""
        if self._model is None:
            from FlagEmbedding import BGEM3FlagModel

            logger.info("embedder.bgem3.loading", model=self._model_name)
            self._model = BGEM3FlagModel(
                self._model_name,
                use_fp16=self._use_fp16,
            )
            logger.info("embedder.bgem3.loaded")
        return self._model

    def _encode_dense_sync(self, texts: list[str]) -> list[list[float]]:
        """Synchronous dense-only encode."""
        model = self._load_model()
        output = model.encode(
            texts,
            batch_size=self._batch_size,
            max_length=self._max_length,
            return_dense=True,
            return_sparse=False,
            return_colbert_vecs=False,
        )
        return output["dense_vecs"].tolist()

    def _encode_all_sync(self, texts: list[str]) -> tuple[list[list[float]], list[tuple[list[int], list[float]]]]:
        """Synchronous unified encode returning (dense, sparse) vectors."""
        model = self._load_model()
        output = model.encode(
            texts,
            batch_size=self._batch_size,
            max_length=self._max_length,
            return_dense=True,
            return_sparse=True,
            return_colbert_vecs=False,
        )
        dense_vecs = output["dense_vecs"].tolist()
        sparse_vecs = self._convert_sparse(output["lexical_weights"])
        return dense_vecs, sparse_vecs

    @staticmethod
    def _convert_sparse(
        lexical_weights: list[dict],
    ) -> list[tuple[list[int], list[float]]]:
        """Convert BGE-M3 lexical weight dicts to (indices, values) tuples."""
        result: list[tuple[list[int], list[float]]] = []
        for weights in lexical_weights:
            indices = [int(k) for k in weights.keys()]
            values = [float(v) for v in weights.values()]
            result.append((indices, values))
        return result

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts (dense only)."""
        if not texts:
            raise ValueError("Cannot embed an empty list of texts.")

        from app.common.metrics import EMBEDDING_CALLS_TOTAL, EMBEDDING_DURATION, track_duration

        with track_duration(EMBEDDING_DURATION, provider="bgem3"):
            result = await asyncio.to_thread(self._encode_dense_sync, texts)

        EMBEDDING_CALLS_TOTAL.labels(provider="bgem3").inc()
        logger.info(
            "embedder.batch_complete",
            provider="bgem3",
            model=self._model_name,
            count=len(texts),
        )
        return result

    async def embed_query(self, text: str) -> list[float]:
        """Embed a single query string."""
        results = await self.embed_texts([text])
        return results[0]

    async def embed_all(self, texts: list[str]) -> tuple[list[list[float]], list[tuple[list[int], list[float]]]]:
        """Unified single-pass embed returning (dense_vectors, sparse_vectors)."""
        if not texts:
            raise ValueError("Cannot embed an empty list of texts.")

        from app.common.metrics import EMBEDDING_CALLS_TOTAL, EMBEDDING_DURATION, track_duration

        with track_duration(EMBEDDING_DURATION, provider="bgem3"):
            dense, sparse = await asyncio.to_thread(self._encode_all_sync, texts)

        EMBEDDING_CALLS_TOTAL.labels(provider="bgem3").inc()
        logger.info(
            "embedder.batch_complete",
            provider="bgem3",
            model=self._model_name,
            count=len(texts),
            mode="unified",
        )
        return dense, sparse

    def embed_sparse_sync(self, texts: list[str]) -> list[tuple[list[int], list[float]]]:
        """Synchronous sparse-only embed for adapter compatibility."""
        model = self._load_model()
        output = model.encode(
            texts,
            batch_size=self._batch_size,
            max_length=self._max_length,
            return_dense=False,
            return_sparse=True,
            return_colbert_vecs=False,
        )
        return self._convert_sparse(output["lexical_weights"])
