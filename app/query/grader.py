"""CRAG-style retrieval relevance grading.

Two-tier approach:
  1. **Heuristic pre-scoring** (~10ms): keyword/entity overlap + Qdrant score.
  2. **LLM grading** (conditional): Only when Tier 1 median < confidence threshold.

Feature-flagged: ``ENABLE_RETRIEVAL_GRADING`` (default ``false``).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from app.common.llm import LLMClient

logger = structlog.get_logger(__name__)


def heuristic_relevance(query: str, chunk_text: str, qdrant_score: float = 0.0) -> float:
    """Fast relevance estimate from keyword overlap + Qdrant score (0.0–1.0).

    Parameters
    ----------
    query:
        The user's query (rewritten or original).
    chunk_text:
        The retrieved chunk text.
    qdrant_score:
        The similarity score from Qdrant (0.0–1.0 for cosine).

    Returns
    -------
    Relevance estimate in [0.0, 1.0].
    """
    # 1. Keyword overlap (case-insensitive)
    query_tokens = set(_tokenize(query))
    chunk_tokens = set(_tokenize(chunk_text))

    if not query_tokens:
        return qdrant_score

    overlap = query_tokens & chunk_tokens
    keyword_score = len(overlap) / len(query_tokens) if query_tokens else 0.0

    # 2. Blend keyword overlap with Qdrant semantic score
    # Qdrant score is the primary signal; keyword overlap supplements it.
    # Use configurable weight — legal documents use synonym-rich vocabulary
    # where keyword overlap penalizes semantically correct results.
    from app.dependencies import get_settings

    kw_weight = get_settings().retrieval_grading_keyword_weight
    combined = (1.0 - kw_weight) * qdrant_score + kw_weight * keyword_score

    return min(max(combined, 0.0), 1.0)


async def grade_retrieval(
    query: str,
    results: list[dict[str, Any]],
    llm: LLMClient | None = None,
    confidence_threshold: float = 0.5,
) -> tuple[list[dict[str, Any]], float, bool]:
    """Grade retrieved chunks for relevance using a two-tier approach.

    Parameters
    ----------
    query:
        The user's query.
    results:
        List of retrieved chunk dicts (must contain ``chunk_text`` and ``score``).
    llm:
        LLM client for Tier 2 grading (optional — if None, only heuristics are used).
    confidence_threshold:
        Median heuristic score below which LLM grading is triggered.

    Returns
    -------
    Tuple of:
      - results with ``relevance_score`` added to each
      - median relevance score (retrieval_confidence)
      - whether LLM grading was triggered
    """
    if not results:
        return results, 1.0, False

    # Tier 1: Heuristic pre-scoring
    for result in results:
        chunk_text = result.get("chunk_text", "")
        qdrant_score = result.get("score", 0.0)
        result["relevance_score"] = heuristic_relevance(query, chunk_text, qdrant_score)

    # Compute median heuristic score
    scores = sorted(r["relevance_score"] for r in results)
    median_score = scores[len(scores) // 2]

    # Tier 2: LLM grading (conditional)
    grading_triggered = False

    if median_score < confidence_threshold and llm is not None:
        grading_triggered = True
        try:
            await _llm_grade(query, results, llm)
            # Recompute median after LLM grading
            scores = sorted(r["relevance_score"] for r in results)
            median_score = scores[len(scores) // 2]
        except Exception:
            logger.warning("grader.llm_grading_failed", exc_info=True)
            # Keep heuristic scores on failure

    logger.info(
        "grader.complete",
        result_count=len(results),
        median_score=round(median_score, 3),
        grading_triggered=grading_triggered,
    )

    return results, median_score, grading_triggered


async def _llm_grade(
    query: str,
    results: list[dict[str, Any]],
    llm: LLMClient,
) -> None:
    """Call LLM to grade chunk relevance and update results in place."""
    from app.query.prompts import GRADING_PROMPT

    # Format chunks for the prompt
    chunks_text = "\n\n".join(f"[{i + 1}] {r.get('chunk_text', '')[:300]}" for i, r in enumerate(results))

    prompt = GRADING_PROMPT.format(query=query, chunks=chunks_text)

    response = await llm.complete(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=len(results) * 10,
        temperature=0.0,
    )

    # Parse scores from response
    scores = _parse_grading_response(response, len(results))
    for i, score in enumerate(scores):
        if score is not None:
            # Normalize from 0-10 to 0-1
            results[i]["relevance_score"] = score / 10.0


def _parse_grading_response(response: str, expected_count: int) -> list[float | None]:
    """Parse numbered score lines from LLM response.

    Handles: ``1: 8``, ``1. 8``, ``[1] 8``
    """
    pattern = re.compile(r"^\s*\[?(\d+)\]?[.:)\s]+(\d+(?:\.\d+)?)", re.MULTILINE)
    matches = pattern.findall(response)

    result: dict[int, float] = {}
    for num_str, score_str in matches:
        num = int(num_str)
        score = float(score_str)
        if 1 <= num <= expected_count and 0 <= score <= 10:
            result[num] = score

    return [result.get(i) for i in range(1, expected_count + 1)]


_STOPWORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "is",
        "was",
        "were",
        "are",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "shall",
        "can",
        "to",
        "of",
        "in",
        "for",
        "on",
        "with",
        "at",
        "by",
        "from",
        "as",
        "into",
        "through",
        "during",
        "before",
        "after",
        "above",
        "below",
        "between",
        "and",
        "but",
        "or",
        "not",
        "no",
        "nor",
        "so",
        "if",
        "then",
        "than",
        "that",
        "this",
        "these",
        "those",
        "it",
        "its",
        "what",
        "which",
        "who",
        "whom",
    }
)


def _tokenize(text: str) -> list[str]:
    """Simple whitespace + punctuation tokenizer, lowercased, stopwords removed."""
    words = re.findall(r"\b[a-z0-9]+(?:'[a-z]+)?\b", text.lower())
    return [w for w in words if w not in _STOPWORDS and len(w) > 1]
