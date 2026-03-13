"""Document summarization at ingestion time.

Generates a 2-3 sentence summary per document from its chunks.
Feature-flagged: ``ENABLE_DOCUMENT_SUMMARIZATION`` (default ``false``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from app.ingestion.prompts import DOC_SUMMARY_PROMPT

if TYPE_CHECKING:
    from app.common.llm import LLMClient

logger = structlog.get_logger(__name__)

# Maximum characters of chunk text to feed into the summary prompt.
# ~4000 tokens ≈ ~16000 chars, but we cap at a safe limit.
_MAX_CONTENT_CHARS = 12000


async def summarize_document(
    chunks: list[Any],
    llm: LLMClient,
    filename: str,
) -> str:
    """Generate a 2-3 sentence document summary from its chunks.

    Gathers the first N chunks (up to ``_MAX_CONTENT_CHARS`` worth of text)
    and asks the LLM to produce a concise summary.

    Parameters
    ----------
    chunks:
        List of Chunk objects from the chunker (must have a ``.text`` attribute).
    llm:
        The LLM client to use for generation.
    filename:
        Original filename for context.

    Returns
    -------
    A 2-3 sentence summary string.
    """
    # Gather chunk texts up to the character limit
    content_parts: list[str] = []
    total_chars = 0
    for chunk in chunks:
        text = chunk.text if hasattr(chunk, "text") else str(chunk)
        if total_chars + len(text) > _MAX_CONTENT_CHARS:
            # Include partial text to fill up to the limit
            remaining = _MAX_CONTENT_CHARS - total_chars
            if remaining > 100:
                content_parts.append(text[:remaining] + "...")
            break
        content_parts.append(text)
        total_chars += len(text)

    if not content_parts:
        return ""

    content = "\n\n".join(content_parts)
    prompt = DOC_SUMMARY_PROMPT.format(filename=filename, content=content)

    summary = await llm.complete(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=200,
        temperature=0.0,
        node_name="document_summarizer",
    )

    # Clean up the summary
    summary = summary.strip()

    logger.info(
        "summarizer.complete",
        filename=filename,
        chunks_used=len(content_parts),
        summary_length=len(summary),
    )

    return summary
