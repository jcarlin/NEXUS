"""Text embedding via OpenAI API (text-embedding-3-large at 1024 dims).

Supports batch embedding for efficiency (up to 64 texts per API call).
Uses tenacity for automatic retry with exponential backoff.
"""

from __future__ import annotations

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


class TextEmbedder:
    """Produce dense text embeddings via the OpenAI embeddings API.

    This class is used during the *embedding* stage of the ingestion
    pipeline (Section 5.4 of CLAUDE.md).  It wraps the ``AsyncOpenAI``
    client and transparently batches large lists of texts.

    Parameters
    ----------
    api_key:
        OpenAI API key.
    model:
        Embedding model name (default ``text-embedding-3-large``).
    dimensions:
        Output vector dimensionality (default 1024).  The model supports
        native dimension reduction via the ``dimensions`` parameter.
    """

    BATCH_SIZE: int = 64  # Max texts per API call

    def __init__(
        self,
        api_key: str,
        model: str = "text-embedding-3-large",
        dimensions: int = 1024,
    ) -> None:
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model
        self._dimensions = dimensions

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of texts, automatically batching if necessary.

        Parameters
        ----------
        texts:
            List of strings to embed.  Empty strings are allowed but
            will produce a zero-content embedding.

        Returns
        -------
        List of embedding vectors (each a list of floats) in the **same
        order** as the input texts.

        Raises
        ------
        openai.APIError
            On non-retryable API errors (after exhausting retries for
            transient failures).
        ValueError
            If *texts* is empty.
        """
        if not texts:
            raise ValueError("Cannot embed an empty list of texts.")

        all_embeddings: list[list[float]] = []

        for batch_start in range(0, len(texts), self.BATCH_SIZE):
            batch = texts[batch_start : batch_start + self.BATCH_SIZE]
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

    async def embed_single(self, text: str) -> list[float]:
        """Convenience method to embed a single text string.

        Returns
        -------
        A single embedding vector (list of floats).
        """
        results = await self.embed_texts([text])
        return results[0]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @retry(
        retry=retry_if_exception_type(
            (APIConnectionError, APITimeoutError, RateLimitError)
        ),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        reraise=True,
        before_sleep=before_sleep_log(logger, "warning"),  # type: ignore[arg-type]
    )
    async def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Call the OpenAI embeddings endpoint for a single batch.

        Automatically retries up to 3 times on transient network errors
        and rate-limit responses.
        """
        response = await self._client.embeddings.create(
            model=self._model,
            input=texts,
            dimensions=self._dimensions,
        )

        # The API may return items out of order — sort by index to
        # guarantee alignment with the input list.
        sorted_data = sorted(response.data, key=lambda item: item.index)
        return [item.embedding for item in sorted_data]
