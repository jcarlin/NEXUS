"""Production quality monitoring for sampled queries.

Computes lightweight quality scores without additional LLM calls:
- ``retrieval_relevance``: average retrieval score from source documents.
- ``faithfulness``: ratio of verified to total cited claims.
- ``citation_density``: claims per 100 words of response text.

Feature-flagged: ``ENABLE_PRODUCTION_QUALITY_MONITORING`` (default ``false``).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class QueryQualityScore(BaseModel):
    """Quality metrics for a single query-response pair."""

    retrieval_relevance: float = Field(ge=0.0, le=1.0, description="Average score from source documents")
    faithfulness: float = Field(ge=0.0, le=1.0, description="Ratio of verified to total cited claims")
    citation_density: float = Field(ge=0.0, description="Claims per 100 words of response")


def score_query_quality(
    query: str,
    response: str,
    source_docs: list[dict[str, Any]],
    cited_claims: list[dict[str, Any]],
) -> QueryQualityScore:
    """Compute lightweight production quality scores.

    This is a pure computation — no LLM calls, no DB access.
    Suitable for fire-and-forget background scoring.

    Parameters
    ----------
    query:
        The original user query.
    response:
        The generated response text.
    source_docs:
        List of source document dicts (must contain ``score`` key).
    cited_claims:
        List of cited claim dicts (must contain ``verified`` key).

    Returns
    -------
    A ``QueryQualityScore`` with all three metrics computed.
    """
    # Retrieval relevance: average score from source documents
    if source_docs:
        scores = [d.get("score", 0.0) for d in source_docs]
        retrieval_relevance = sum(scores) / len(scores)
        # Clamp to [0, 1]
        retrieval_relevance = max(0.0, min(1.0, retrieval_relevance))
    else:
        retrieval_relevance = 0.0

    # Faithfulness: ratio of verified claims
    if cited_claims:
        verified_count = sum(1 for c in cited_claims if c.get("verified", False))
        faithfulness = verified_count / len(cited_claims)
    else:
        # No claims = neutral faithfulness (nothing to verify)
        faithfulness = 1.0

    # Citation density: claims per 100 words
    word_count = len(response.split()) if response else 0
    if word_count > 0 and cited_claims:
        citation_density = (len(cited_claims) / word_count) * 100
    else:
        citation_density = 0.0

    return QueryQualityScore(
        retrieval_relevance=round(retrieval_relevance, 4),
        faithfulness=round(faithfulness, 4),
        citation_density=round(citation_density, 4),
    )
