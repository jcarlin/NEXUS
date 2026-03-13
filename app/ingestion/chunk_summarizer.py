"""Chunk summarization for multi-representation indexing (T2-11).

Generates a one-sentence summary per chunk.  Summaries are embedded
separately and stored as a third named vector (``summary``) in Qdrant,
enabling triple RRF fusion (dense + sparse + summary).

Feature-flagged: ``ENABLE_MULTI_REPRESENTATION`` (default ``false``).
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

# Truncate chunk text in the prompt to this many characters
_MAX_CHUNK_TEXT_CHARS = 1000


async def summarize_chunks(
    chunks: list[Chunk],
    llm: LLMClient,
    concurrency: int = 4,
) -> list[Chunk]:
    """Add ``chunk_summary`` to each chunk's metadata.

    Parameters
    ----------
    chunks:
        Chunks to summarize (modified in place).
    llm:
        LLM client for generation.
    concurrency:
        Maximum number of concurrent LLM calls.

    Returns
    -------
    The same list of chunks with ``chunk_summary`` populated in metadata.
    """
    if not chunks:
        return []

    sem = asyncio.Semaphore(concurrency)

    async def _summarize_one(chunk: Chunk) -> None:
        async with sem:
            text = chunk.text[:_MAX_CHUNK_TEXT_CHARS]
            if len(chunk.text) > _MAX_CHUNK_TEXT_CHARS:
                text += "..."

            prompt = CHUNK_SUMMARY_PROMPT.format(chunk_text=text)

            try:
                response = await llm.complete(
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=100,
                    temperature=0.0,
                    node_name="chunk_summarizer",
                )
                chunk.metadata["chunk_summary"] = response.strip()
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
