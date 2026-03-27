"""Per-request retrieval strategy override resolution.

Allows users to override retrieval-related feature flags and numeric
parameters on a per-chat basis.  Overrides travel in graph state, never
mutate the Settings singleton.

Precedence: request override > global setting, with DI-gate guard.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

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


# ---------------------------------------------------------------------------
# Numeric parameter overrides
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParamMeta:
    """Metadata for an overridable numeric parameter."""

    display_name: str
    description: str
    param_type: str  # "int" | "float"
    default_attr: str  # attribute name on Settings
    min_value: int | float
    max_value: int | float
    step: float | None = None


OVERRIDABLE_PARAMS: dict[str, ParamMeta] = {
    "retrieval_text_limit": ParamMeta(
        display_name="Text Result Limit",
        description="Maximum number of text/vector results to retrieve",
        param_type="int",
        default_attr="retrieval_text_limit",
        min_value=5,
        max_value=100,
        step=5,
    ),
    "retrieval_graph_limit": ParamMeta(
        display_name="Graph Result Limit",
        description="Maximum number of graph traversal results",
        param_type="int",
        default_attr="retrieval_graph_limit",
        min_value=5,
        max_value=50,
        step=5,
    ),
    "multi_query_count": ParamMeta(
        display_name="Query Variants",
        description="Number of expanded query variants for multi-query",
        param_type="int",
        default_attr="multi_query_count",
        min_value=1,
        max_value=10,
        step=1,
    ),
    "hyde_blend_ratio": ParamMeta(
        display_name="HyDE Blend Ratio",
        description="Blend weight between HyDE and raw query embeddings (1.0 = pure HyDE)",
        param_type="float",
        default_attr="hyde_blend_ratio",
        min_value=0.0,
        max_value=1.0,
        step=0.1,
    ),
    "reranker_top_n": ParamMeta(
        display_name="Reranker Top-N",
        description="Number of results to keep after cross-encoder reranking",
        param_type="int",
        default_attr="reranker_top_n",
        min_value=3,
        max_value=50,
        step=1,
    ),
    "query_entity_threshold": ParamMeta(
        display_name="Entity Threshold",
        description="Confidence threshold for entity extraction (lower = more entities)",
        param_type="float",
        default_attr="query_entity_threshold",
        min_value=0.0,
        max_value=1.0,
        step=0.05,
    ),
    "self_reflection_faithfulness_threshold": ParamMeta(
        display_name="Faithfulness Threshold",
        description="Faithfulness score below which self-reflection retries",
        param_type="float",
        default_attr="self_reflection_faithfulness_threshold",
        min_value=0.0,
        max_value=1.0,
        step=0.1,
    ),
}


def get_override_category(flag_name: str) -> OverrideCategory:
    """Return the override category for a flag."""
    if flag_name in _DI_GATED_FLAGS:
        return OverrideCategory.DI_GATED
    return OverrideCategory.LOGIC


def resolve_flag(
    flag_name: str,
    settings: Settings,
    overrides: dict[str, Any] | None,
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

    # Track that this override was applied (for trace panel)
    if requested != global_value:
        from app.query.trace import track_override_usage

        track_override_usage(flag_name)

    return requested


def resolve_param(
    param_name: str,
    settings: Settings,
    overrides: dict[str, Any] | None,
) -> int | float:
    """Resolve a numeric parameter with per-request override precedence.

    Returns the override value if present, otherwise the global setting.
    """
    global_value: int | float = getattr(settings, param_name)

    if not overrides or param_name not in overrides:
        return global_value

    override_value = overrides[param_name]

    # Track that this override was applied (for trace panel)
    if override_value != global_value:
        from app.query.trace import track_override_usage

        track_override_usage(param_name)

    return override_value


def validate_overrides(
    overrides: dict[str, Any] | None,
    settings: Settings,
) -> dict[str, bool | int | float]:
    """Validate and normalize an overrides dict.

    Handles both boolean flags and numeric parameters.
    Strips None values, rejects unknown keys, applies DI-gate rules and range checks.
    Returns a clean dict with only effective overrides.
    """
    if not overrides:
        return {}

    effective: dict[str, bool | int | float] = {}
    for key, value in overrides.items():
        if value is None:
            continue

        # Boolean flag
        if key in OVERRIDABLE_FLAGS:
            if not isinstance(value, bool):
                continue
            # DI-gate: reject enabling a flag whose model isn't loaded
            if key in _DI_GATED_FLAGS and value and not getattr(settings, key):
                logger.warning("override.di_gate_rejected", flag=key)
                continue
            effective[key] = value

        # Numeric parameter
        elif key in OVERRIDABLE_PARAMS:
            meta = OVERRIDABLE_PARAMS[key]
            if not isinstance(value, int | float):
                continue
            # Clamp to valid range
            clamped = max(meta.min_value, min(meta.max_value, value))
            # Cast to correct type
            if meta.param_type == "int":
                clamped = int(clamped)
            else:
                clamped = float(clamped)
            effective[key] = clamped

        # Unknown key — silently skip

    return effective
