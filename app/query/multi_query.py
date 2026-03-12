"""Multi-query expansion for broader legal vocabulary coverage.

Generates alternative formulations of a query to address vocabulary mismatch
(e.g., "deal" vs. "transaction" vs. "agreement") and improve retrieval recall.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from app.common.llm import LLMClient

logger = structlog.get_logger(__name__)

MULTI_QUERY_PROMPT = """\
You are a legal document search optimizer. Generate {count} alternative \
formulations of the following query to improve document retrieval coverage.

Each reformulation should:
- Use different legal vocabulary (formal vs. informal, abbreviation vs. full name)
- Capture synonyms and related legal terms (e.g., "agreement" ↔ "contract" ↔ "deal")
- Vary the phrasing while preserving the original intent
- Consider both technical legal language and plain language

{term_map_context}Original query: {query}

Return a JSON array of {count} strings (alternative queries only, NOT the original).
Example: ["reformulation 1", "reformulation 2", "reformulation 3"]"""


async def expand_query(
    query: str,
    llm: LLMClient,
    *,
    term_map: dict[str, str] | None = None,
    count: int = 3,
) -> list[str]:
    """Generate *count* reformulations of *query* for parallel retrieval.

    Args:
        query: The original user query.
        llm: LLM client for generating reformulations.
        term_map: Optional alias/term map from case context for expansion hints.
        count: Number of variants to generate.

    Returns:
        List of variant queries (original NOT included).
    """
    term_context = ""
    if term_map:
        aliases = ", ".join(f'"{k}" → "{v}"' for k, v in list(term_map.items())[:10])
        term_context = f"Known aliases and terms: {aliases}\n\n"

    prompt = MULTI_QUERY_PROMPT.format(
        count=count,
        query=query,
        term_map_context=term_context,
    )

    try:
        raw = await llm.complete(
            [{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0.3,
            node_name="multi_query_expand",
        )

        # Parse JSON array from response
        variants = _parse_variants(raw)
        if not variants:
            logger.warning("multi_query.no_variants_parsed")
            return []

        logger.info("multi_query.expanded", original=query[:80], variant_count=len(variants))
        return variants[:count]

    except Exception:
        logger.warning("multi_query.expand_failed", exc_info=True)
        return []


def _parse_variants(raw: str) -> list[str]:
    """Best-effort parse a JSON string array from LLM output."""
    # Try direct JSON parse
    try:
        parsed = json.loads(raw.strip())
        if isinstance(parsed, list):
            return [str(v) for v in parsed if isinstance(v, str) and len(v) > 5]
    except (json.JSONDecodeError, TypeError):
        pass

    # Try finding JSON array in response
    start = raw.find("[")
    end = raw.rfind("]")
    if start != -1 and end != -1 and end > start:
        try:
            parsed = json.loads(raw[start : end + 1])
            if isinstance(parsed, list):
                return [str(v) for v in parsed if isinstance(v, str) and len(v) > 5]
        except (json.JSONDecodeError, TypeError):
            pass

    return []
