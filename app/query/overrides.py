"""Per-request retrieval strategy override resolution.

Allows users to override retrieval-related feature flags on a per-chat basis.
Overrides travel in graph state, never mutate the Settings singleton.

Precedence: request override > global setting, with DI-gate guard.
"""

from __future__ import annotations

from enum import StrEnum

import structlog

from app.config import Settings

logger = structlog.get_logger(__name__)


class OverrideCategory(StrEnum):
    """Classification of overridable flags."""

    LOGIC = "logic"  # Pure control flow — freely toggleable
    DI_GATED = "di_gated"  # Requires loaded model — can only disable


# Flags that require a loaded model/resource — can only be DISABLED per-request.
# Cannot ENABLE if globally off (model not loaded).
_DI_GATED_FLAGS: frozenset[str] = frozenset(
    {
        "enable_reranker",
        "enable_sparse_embeddings",
        "enable_visual_embeddings",
    }
)

# All flags valid for per-request override.
OVERRIDABLE_FLAGS: frozenset[str] = frozenset(
    {
        # Logic-branch (freely toggleable)
        "enable_hyde",
        "enable_multi_query_expansion",
        "enable_retrieval_grading",
        "enable_citation_verification",
        "enable_self_reflection",
        "enable_text_to_cypher",
        "enable_text_to_sql",
        "enable_question_decomposition",
        "enable_prompt_routing",
        "enable_adaptive_retrieval_depth",
        # DI-gated (can only disable if globally enabled)
        "enable_reranker",
        "enable_sparse_embeddings",
        "enable_visual_embeddings",
    }
)

# User-facing labels for each overridable flag.
OVERRIDE_LABELS: dict[str, str] = {
    "enable_hyde": "HyDE Search",
    "enable_multi_query_expansion": "Query Variants",
    "enable_retrieval_grading": "Relevance Filter",
    "enable_citation_verification": "Verify Citations",
    "enable_self_reflection": "Answer Refinement",
    "enable_text_to_cypher": "Graph Search",
    "enable_text_to_sql": "SQL Search",
    "enable_question_decomposition": "Decompose Questions",
    "enable_prompt_routing": "Smart Prompts",
    "enable_adaptive_retrieval_depth": "Adaptive Depth",
    "enable_reranker": "Reranker",
    "enable_sparse_embeddings": "Sparse Retrieval",
    "enable_visual_embeddings": "Visual Search",
}

# Short descriptions for each overridable flag.
OVERRIDE_DESCRIPTIONS: dict[str, str] = {
    "enable_hyde": "Generate hypothetical answer, embed it for better retrieval",
    "enable_multi_query_expansion": "Expand query into alternative phrasings",
    "enable_retrieval_grading": "CRAG-style grading to filter weak chunks",
    "enable_citation_verification": "Post-generation citation accuracy check",
    "enable_self_reflection": "Retry loop when answer faithfulness is low",
    "enable_text_to_cypher": "Enable text-to-Cypher knowledge graph queries",
    "enable_text_to_sql": "Enable text-to-SQL document queries",
    "enable_question_decomposition": "Break complex questions into sub-queries",
    "enable_prompt_routing": "Classify query type for optimized prompts",
    "enable_adaptive_retrieval_depth": "Dynamic retrieval limits by query complexity",
    "enable_reranker": "Cross-encoder reranking of retrieval results",
    "enable_sparse_embeddings": "BM42/SPLADE sparse vectors for hybrid retrieval",
    "enable_visual_embeddings": "ColQwen2.5 visual embedding and reranking",
}


def get_override_category(flag_name: str) -> OverrideCategory:
    """Return the override category for a flag."""
    if flag_name in _DI_GATED_FLAGS:
        return OverrideCategory.DI_GATED
    return OverrideCategory.LOGIC


def resolve_flag(
    flag_name: str,
    settings: Settings,
    overrides: dict[str, bool] | None,
) -> bool:
    """Resolve a single flag value with per-request override precedence.

    Rules:
    - If no overrides or flag not in overrides: return global setting
    - Logic-branch flags: override freely (True or False)
    - DI-gated flags: can only disable (override=False when global=True)
      Cannot enable a DI-gated flag that's globally off (model not loaded)
    """
    global_value: bool = getattr(settings, flag_name)

    if not overrides or flag_name not in overrides:
        return global_value

    requested = overrides[flag_name]

    if flag_name in _DI_GATED_FLAGS and requested and not global_value:
        # Cannot enable — model not loaded
        logger.warning(
            "override.di_gate_blocked",
            flag=flag_name,
            reason="model_not_loaded",
        )
        return False

    return requested


def validate_overrides(
    overrides: dict[str, bool | None] | None,
    settings: Settings,
) -> dict[str, bool]:
    """Validate and normalize an overrides dict.

    Strips None values, rejects unknown flags, applies DI-gate rules.
    Returns a clean dict with only effective overrides.
    """
    if not overrides:
        return {}

    effective: dict[str, bool] = {}
    for flag_name, value in overrides.items():
        if value is None:
            continue
        if flag_name not in OVERRIDABLE_FLAGS:
            continue

        # DI-gate: reject enabling a flag whose model isn't loaded
        if flag_name in _DI_GATED_FLAGS and value and not getattr(settings, flag_name):
            logger.warning(
                "override.di_gate_rejected",
                flag=flag_name,
            )
            continue

        effective[flag_name] = value

    return effective
