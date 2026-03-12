"""Question decomposition for complex multi-part legal queries.

Breaks complex questions into independent sub-questions, retrieves
evidence for each, and merges results for comprehensive coverage.
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

import structlog
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from app.common.llm import LLMClient
    from app.query.retriever import HybridRetriever

logger = structlog.get_logger(__name__)


class SubQuestion(BaseModel):
    """An independent sub-question derived from a complex query."""

    question: str = Field(..., description="The sub-question text")
    aspect: str = Field(..., description="What aspect this covers (e.g., 'who', 'when', 'what action')")
    reasoning: str = Field(..., description="Why this sub-question is needed")


class DecompositionResult(BaseModel):
    """Result of question decomposition."""

    sub_questions: list[SubQuestion] = Field(default_factory=list)
    is_complex: bool = Field(default=False, description="Whether the original query was complex enough to decompose")


DECOMPOSE_QUESTION_PROMPT = """\
You are a legal investigation analyst. Determine whether the following \
question is complex (multi-part) and, if so, break it into 2-4 independent \
sub-questions that can be researched separately.

A question is complex if it:
- Asks about multiple distinct aspects (who, what, when, why)
- Combines questions about different entities or events
- Requires evidence from different document types or time periods

If the question is simple (single aspect, single entity), set is_complex to false \
and return an empty sub_questions list.

Question: {query}

Respond as JSON:
{{
  "is_complex": true/false,
  "sub_questions": [
    {{"question": "...", "aspect": "...", "reasoning": "..."}}
  ]
}}"""


async def decompose_question(
    query: str,
    llm: LLMClient,
) -> DecompositionResult:
    """Decompose a complex query into sub-questions using Instructor-style extraction.

    Returns a ``DecompositionResult`` with ``is_complex=False`` for simple
    queries (no decomposition needed).
    """
    prompt = DECOMPOSE_QUESTION_PROMPT.format(query=query)

    try:
        raw = await llm.complete(
            [{"role": "user", "content": prompt}],
            max_tokens=800,
            temperature=0.0,
            node_name="decompose_question",
        )

        # Parse structured output
        parsed = _parse_decomposition(raw)
        logger.info(
            "decomposer.result",
            is_complex=parsed.is_complex,
            sub_question_count=len(parsed.sub_questions),
        )
        return parsed

    except Exception:
        logger.warning("decomposer.failed", exc_info=True)
        return DecompositionResult(is_complex=False)


async def retrieve_for_sub_questions(
    sub_questions: list[SubQuestion],
    retriever: HybridRetriever,
    *,
    filters: dict[str, Any] | None = None,
    exclude_privilege: list[str] | None = None,
    dataset_doc_ids: list[str] | None = None,
    limit_per_question: int = 10,
) -> list[dict[str, Any]]:
    """Run parallel retrieval for each sub-question, deduplicate, and merge.

    Returns a merged, deduplicated list of results sorted by score.
    """
    coros = [
        retriever.retrieve_text(
            sq.question,
            limit=limit_per_question,
            filters=filters,
            exclude_privilege_statuses=exclude_privilege or None,
            dataset_doc_ids=dataset_doc_ids,
        )
        for sq in sub_questions
    ]

    all_results = await asyncio.gather(*coros, return_exceptions=True)

    # Deduplicate by chunk ID, keep highest score
    seen: dict[str, dict[str, Any]] = {}
    for batch in all_results:
        if isinstance(batch, BaseException):
            logger.warning("decomposer.retrieval_error", error=str(batch))
            continue
        for r in batch:
            rid = r.get("id", "")
            if rid not in seen or r.get("score", 0) > seen[rid].get("score", 0):
                seen[rid] = r

    merged = sorted(seen.values(), key=lambda r: r.get("score", 0), reverse=True)
    logger.debug(
        "decomposer.retrieval_merged",
        sub_questions=len(sub_questions),
        total_results=len(merged),
    )
    return merged


def _parse_decomposition(raw: str) -> DecompositionResult:
    """Best-effort parse a DecompositionResult from LLM output."""
    # Try direct JSON parse
    try:
        data = json.loads(raw.strip())
        return DecompositionResult(**data)
    except Exception:
        pass

    # Try finding JSON object in response
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            data = json.loads(raw[start : end + 1])
            return DecompositionResult(**data)
        except Exception:
            pass

    return DecompositionResult(is_complex=False)
