"""Document summarization at ingestion time (T2-12).

Generates a 2-3 sentence summary per document from its first N chunks.
Feature-flagged: ``ENABLE_DOCUMENT_SUMMARIZATION`` (default ``false``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from app.ingestion.prompts import DOC_SUMMARY_PROMPT

if TYPE_CHECKING:
    from app.common.llm import LLMClient
    from app.ingestion.chunker import Chunk

logger = structlog.get_logger(__name__)

# Maximum characters of chunk content to include in the prompt
_MAX_CONTENT_CHARS = 8000


async def summarize_document(
    chunks: list[Chunk],
    llm: LLMClient,
    filename: str,
) -> str:
    """Generate a 2-3 sentence document summary from its chunks.

    Parameters
    ----------
    chunks:
        All chunks produced by the chunker for this document.
    llm:
        LLM client for generation.
    filename:
        Original filename, included in the prompt for context.

    Returns
    -------
    A 2-3 sentence summary string, or empty string if no chunks.
    """
    if not chunks:
        return ""

    # Gather content from first N chunks up to the character limit
    content_parts: list[str] = []
    total_chars = 0
    for chunk in chunks:
        if total_chars >= _MAX_CONTENT_CHARS:
            break
        remaining = _MAX_CONTENT_CHARS - total_chars
        text = chunk.text[:remaining]
        content_parts.append(text)
        total_chars += len(text)

    content = "\n\n".join(content_parts)
    if total_chars >= _MAX_CONTENT_CHARS:
        content += "..."

    prompt = DOC_SUMMARY_PROMPT.format(filename=filename, content=content)

    response = await llm.complete(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=200,
        temperature=0.0,
        node_name="document_summarizer",
    )

    summary = response.strip()
    logger.info(
        "summarizer.complete",
        filename=filename,
        summary_length=len(summary),
        chunks_used=len(content_parts),
    )
    return summary
