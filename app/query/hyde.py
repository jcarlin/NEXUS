"""HyDE (Hypothetical Document Embeddings) for vocabulary-gap bridging.

Generates a hypothetical document passage that answers the user's query,
then embeds that passage instead of the raw query for dense retrieval.
The raw query is still used for sparse (BM42) retrieval to preserve
lexical matching.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from app.query.prompts import HYDE_PROMPT

if TYPE_CHECKING:
    from app.common.llm import LLMClient

logger = structlog.get_logger(__name__)


async def generate_hypothetical_document(
    query: str,
    llm: LLMClient,
    *,
    matter_context: str = "",
) -> str:
    """Generate a hypothetical document passage that answers *query*.

    Args:
        query: The user's natural language question.
        llm: LLM client for generation.
        matter_context: Optional case/matter context for tailoring the passage.

    Returns:
        A 2-3 sentence hypothetical passage from a legal document.

    Raises:
        Exception: Propagates LLM errors (caller should handle).
    """
    context_block = f"Context about this legal matter: {matter_context}\n\n" if matter_context else ""

    prompt = HYDE_PROMPT.format(
        query=query,
        matter_context=context_block,
    )

    hypothetical = await llm.complete(
        [{"role": "user", "content": prompt}],
        max_tokens=200,
        temperature=0.3,
        node_name="hyde_generate",
    )

    hypothetical = hypothetical.strip()
    logger.info(
        "hyde.generated",
        query_len=len(query),
        hypothetical_len=len(hypothetical),
    )
    return hypothetical
