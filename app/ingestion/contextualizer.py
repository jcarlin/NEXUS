"""Contextual chunk enrichment via batched LLM calls.

For each chunk, generates a concise context sentence describing the chunk's
content and role in the document.  The context prefix is prepended to the
chunk text before embedding, improving retrieval precision.

Feature-flagged: ``ENABLE_CONTEXTUAL_CHUNKS`` (default ``false``).
"""

from __future__ import annotations

import asyncio
import re
from typing import TYPE_CHECKING

import structlog

from app.ingestion.prompts import CONTEXT_SYSTEM_PROMPT, CONTEXT_USER_PROMPT

if TYPE_CHECKING:
    from app.common.llm import LLMClient
    from app.ingestion.chunker import Chunk

logger = structlog.get_logger(__name__)

# Max words for a context prefix — truncate if LLM over-generates
_MAX_PREFIX_WORDS = 50


class ChunkContextualizer:
    """Add LLM-generated context prefixes to chunks via batched calls."""

    def __init__(
        self,
        llm: LLMClient,
        batch_size: int = 20,
        concurrency: int = 4,
        max_tokens: int = 100,
    ) -> None:
        self._llm = llm
        self._batch_size = batch_size
        self._concurrency = concurrency
        self._max_tokens_per_chunk = max_tokens

    async def contextualize_batch(
        self,
        chunks: list[Chunk],
        doc_title: str,
        doc_type: str,
        doc_author: str | None = None,
        doc_date: str | None = None,
        min_quality_score: float = 0.2,
    ) -> list[Chunk]:
        """Add context_prefix to each chunk via batched LLM calls.

        Parameters
        ----------
        chunks:
            Chunks to contextualize (modified in place).
        doc_title:
            Document title/filename for context.
        doc_type:
            Document type (email, deposition, contract, etc.).
        doc_author:
            Document author (if known).
        doc_date:
            Document date (if known).
        min_quality_score:
            Skip chunks with quality_score below this threshold.

        Returns
        -------
        The same list of chunks with ``context_prefix`` populated.
        """
        # Partition into contextualizable vs skip
        to_process: list[tuple[int, Chunk]] = []
        for i, chunk in enumerate(chunks):
            qs = chunk.metadata.get("quality_score")
            if qs is not None and qs < min_quality_score:
                continue
            to_process.append((i, chunk))

        if not to_process:
            return chunks

        # Split into batches
        batches: list[list[tuple[int, Chunk]]] = []
        for start in range(0, len(to_process), self._batch_size):
            batches.append(to_process[start : start + self._batch_size])

        # Process batches with concurrency limit
        sem = asyncio.Semaphore(self._concurrency)

        async def _process_batch(batch: list[tuple[int, Chunk]]) -> None:
            async with sem:
                await self._contextualize_one_batch(batch, doc_title, doc_type, doc_author, doc_date)

        await asyncio.gather(*[_process_batch(b) for b in batches])

        contextualized = sum(1 for c in chunks if c.context_prefix is not None)
        logger.info(
            "contextualizer.complete",
            total_chunks=len(chunks),
            contextualized=contextualized,
            skipped=len(chunks) - len(to_process),
        )

        return chunks

    async def _contextualize_one_batch(
        self,
        batch: list[tuple[int, Chunk]],
        doc_title: str,
        doc_type: str,
        doc_author: str | None,
        doc_date: str | None,
    ) -> None:
        """Call LLM for one batch of chunks and parse results."""
        # Format chunks as numbered list
        numbered_lines: list[str] = []
        for seq, (_, chunk) in enumerate(batch, 1):
            # Truncate chunk text to ~300 chars to keep prompt manageable
            preview = chunk.text[:300]
            if len(chunk.text) > 300:
                preview += "..."
            numbered_lines.append(f"[{seq}] {preview}")

        numbered_chunks = "\n\n".join(numbered_lines)

        user_prompt = CONTEXT_USER_PROMPT.format(
            title=doc_title,
            doc_type=doc_type,
            author=doc_author or "Unknown",
            date=doc_date or "Unknown",
            numbered_chunks=numbered_chunks,
        )

        # Estimate max output tokens: ~30 tokens per chunk context sentence
        max_tokens = max(len(batch) * 30, self._max_tokens_per_chunk)

        try:
            response = await self._llm.complete(
                messages=[
                    {"role": "system", "content": CONTEXT_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=max_tokens,
                temperature=0.0,
            )

            # Parse numbered responses
            prefixes = _parse_numbered_response(response, len(batch))

            for (seq_idx, (_, chunk)), prefix in zip(enumerate(batch), prefixes):
                if prefix:
                    # Truncate overly long prefixes
                    words = prefix.split()
                    if len(words) > _MAX_PREFIX_WORDS:
                        prefix = " ".join(words[:_MAX_PREFIX_WORDS]) + "..."
                    chunk.context_prefix = prefix

        except Exception:
            logger.warning(
                "contextualizer.batch_failed",
                batch_size=len(batch),
                exc_info=True,
            )
            # Graceful degradation: chunks keep context_prefix = None


def _parse_numbered_response(response: str, expected_count: int) -> list[str]:
    """Parse numbered context sentences from LLM response.

    Handles formats like:
    - ``[1] Context sentence here.``
    - ``1. Context sentence here.``
    - ``1: Context sentence here.``
    """
    # Try to match numbered lines
    pattern = re.compile(r"^\s*\[?(\d+)\]?[.:\-)\s]+(.+)$", re.MULTILINE)
    matches = pattern.findall(response)

    if not matches:
        # Fallback: split on newlines and hope for the best
        lines = [ln.strip() for ln in response.strip().split("\n") if ln.strip()]
        return lines[:expected_count] + [""] * max(0, expected_count - len(lines))

    # Build a mapping from number to text
    result_map: dict[int, str] = {}
    for num_str, text in matches:
        num = int(num_str)
        if 1 <= num <= expected_count:
            result_map[num] = text.strip()

    return [result_map.get(i, "") for i in range(1, expected_count + 1)]
