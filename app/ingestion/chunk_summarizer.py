"""Chunk summarization for multi-representation indexing.

Generates a one-sentence summary per chunk. The summary embedding is stored
as a third named vector in Qdrant alongside dense and sparse, enabling
retrieval on summaries while returning full chunk text.

Feature-flagged: ``ENABLE_MULTI_REPRESENTATION`` (default ``false``).
Follows the batched async worker pattern from ``contextualizer.py``.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import structlog

from app.ingestion.prompts import CHUNK_SUMMARY_PROMPT

if TYPE_CHECKING:
    from app.common.llm import LLMClient
    from app.ingestion.chunker import Chunk

logger = structlog.get_logger(__name__)


async def summarize_chunks(
    chunks: list[Chunk],
    llm: LLMClient,
    concurrency: int = 4,
) -> list[Chunk]:
    """Add ``chunk_summary`` to each chunk's metadata via concurrent LLM calls.

    Parameters
    ----------
    chunks:
        List of Chunk objects to summarize (modified in place).
    llm:
        The LLM client to use for generation.
    concurrency:
        Maximum number of concurrent LLM calls.

    Returns
    -------
    The same list of chunks with ``chunk_summary`` added to metadata.
    """
    if not chunks:
        return chunks

    sem = asyncio.Semaphore(concurrency)

    async def _summarize_one(chunk: Chunk) -> None:
        async with sem:
            prompt = CHUNK_SUMMARY_PROMPT.format(chunk_text=chunk.text[:1000])
            try:
                summary = await llm.complete(
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=80,
                    temperature=0.0,
                    node_name="chunk_summarizer",
                )
                chunk.metadata["chunk_summary"] = summary.strip()
            except Exception:
                logger.warning(
                    "chunk_summarizer.failed",
                    chunk_index=chunk.chunk_index,
                    exc_info=True,
                )
                chunk.metadata["chunk_summary"] = ""

    await asyncio.gather(*[_summarize_one(c) for c in chunks])

    summarized = sum(1 for c in chunks if c.metadata.get("chunk_summary"))
    logger.info(
        "chunk_summarizer.complete",
        total_chunks=len(chunks),
        summarized=summarized,
    )

    return chunks
