"""Pydantic v2 schemas for evaluation datasets and metric results."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Dataset enums
# ---------------------------------------------------------------------------


class QuestionCategory(StrEnum):
    FACTUAL = "factual"
    ANALYTICAL = "analytical"
    EXPLORATORY = "exploratory"
    TIMELINE = "timeline"


class QuestionDifficulty(StrEnum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class AdversarialCategory(StrEnum):
    FALSE_PREMISE = "false_premise"
    PRIVILEGE_TRICK = "privilege_trick"
    AMBIGUOUS_ENTITY = "ambiguous_entity"
    OVERTURNED_PRECEDENT = "overturned_precedent"
    ENTITY_CONFUSION = "entity_confusion"
    TEMPORAL_CONFUSION = "temporal_confusion"
    SCOPE_VIOLATION = "scope_violation"
    PRIVILEGE_BOUNDARY = "privilege_boundary"
    COMPOUND_TRAP = "compound_trap"


class LegalBenchTaskType(StrEnum):
    ISSUE_SPOTTING = "issue_spotting"
    RULE_RECALL = "rule_recall"
    RULE_APPLICATION = "rule_application"
    INTERPRETATION = "interpretation"
    RHETORICAL_UNDERSTANDING = "rhetorical_understanding"


class RetrievalMode(StrEnum):
    DENSE = "dense"
    SPARSE = "sparse"
    HYBRID = "hybrid"
    VISUAL = "visual"
    VISUAL_FUSION = "visual_fusion"


class EvaluationMode(StrEnum):
    DRY_RUN = "dry_run"
    FULL = "full"


# ---------------------------------------------------------------------------
# Dataset item schemas
# ---------------------------------------------------------------------------


class ExpectedCitation(BaseModel):
    """A citation range within a source document."""

    document_id: str = Field(..., description="Document filename or UUID")
    page_start: int = Field(..., ge=1)
    page_end: int = Field(..., ge=1)


class GroundTruthItem(BaseModel):
    """A single ground-truth Q&A pair with expected retrieval targets."""

    id: str
    question: str
    expected_answer: str
    category: QuestionCategory
    difficulty: QuestionDifficulty
    expected_documents: list[str] = Field(..., description="Document filenames or UUIDs that should be retrieved")
    expected_citations: list[ExpectedCitation] = Field(default_factory=list)
    matter_id: str | None = None
    tags: list[str] = Field(default_factory=list)


class AdversarialItem(BaseModel):
    """An adversarial test case designed to probe failure modes."""

    id: str
    question: str
    category: AdversarialCategory
    expected_behavior: str = Field(
        ..., description="What the system should do (e.g., 'refuse to answer', 'flag ambiguity')"
    )
    should_answer: bool = Field(..., description="Whether the system should produce a substantive answer")
    trap_document_ids: list[str] = Field(
        default_factory=list,
        description="Documents that would be wrong to cite",
    )


class LegalBenchItem(BaseModel):
    """A legal reasoning task inspired by the LegalBench benchmark."""

    id: str
    question: str
    task_type: LegalBenchTaskType
    expected_answer: str
    expected_documents: list[str] = Field(default_factory=list)
    scoring_rubric: str = Field(..., description="How to evaluate the answer (keywords, reasoning steps, etc.)")


class EvaluationDataset(BaseModel):
    """Complete evaluation dataset with all test categories."""

    version: str = "1.0"
    ground_truth: list[GroundTruthItem] = Field(default_factory=list)
    adversarial: list[AdversarialItem] = Field(default_factory=list)
    legalbench: list[LegalBenchItem] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Metric result schemas
# ---------------------------------------------------------------------------


class RetrievalMetrics(BaseModel):
    """Retrieval quality metrics for a single mode (dense/sparse/hybrid)."""

    mode: RetrievalMode
    mrr_at_10: float = Field(..., ge=0.0, le=1.0)
    recall_at_10: float = Field(..., ge=0.0, le=1.0)
    ndcg_at_10: float = Field(..., ge=0.0, le=1.0)
    precision_at_10: float = Field(..., ge=0.0, le=1.0)
    num_queries: int = Field(..., ge=0)


class GenerationMetrics(BaseModel):
    """LLM generation quality metrics (RAGAS-based)."""

    faithfulness: float = Field(..., ge=0.0, le=1.0)
    answer_relevancy: float = Field(..., ge=0.0, le=1.0)
    context_precision: float = Field(..., ge=0.0, le=1.0)
    num_queries: int = Field(..., ge=0)


class CitationMetrics(BaseModel):
    """Citation provenance metrics."""

    citation_accuracy: float = Field(..., ge=0.0, le=1.0)
    hallucination_rate: float = Field(..., ge=0.0, le=1.0)
    post_rationalization_rate: float = Field(..., ge=0.0, le=1.0)
    total_claims: int = Field(..., ge=0)
    supported_claims: int = Field(..., ge=0)
    unsupported_claims: int = Field(..., ge=0)
    post_rationalized_claims: int = Field(..., ge=0)


class AdversarialSummary(BaseModel):
    """Summary of adversarial test results."""

    total: int = Field(..., ge=0)
    passed: int = Field(..., ge=0)
    failed: int = Field(..., ge=0)
    pass_rate: float = Field(..., ge=0.0, le=1.0)


class LegalBenchSummary(BaseModel):
    """Summary of LegalBench task results."""

    total: int = Field(..., ge=0)
    passed: int = Field(..., ge=0)
    failed: int = Field(..., ge=0)
    pass_rate: float = Field(..., ge=0.0, le=1.0)


class EvaluationResult(BaseModel):
    """Complete evaluation run result."""

    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    mode: EvaluationMode
    config_overrides: dict[str, str] = Field(
        default_factory=dict,
        description="Config overrides applied for this run (empty = baseline)",
    )
    retrieval: list[RetrievalMetrics] = Field(default_factory=list)
    generation: GenerationMetrics | None = None
    citation: CitationMetrics | None = None
    adversarial_summary: AdversarialSummary | None = None
    legalbench_summary: LegalBenchSummary | None = None
    passed: bool = False
    gate_failures: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Tuning comparison schemas
# ---------------------------------------------------------------------------


class TuningConfig(BaseModel):
    """A named configuration for a tuning experiment."""

    name: str = Field(..., description="Human-readable config name (e.g., 'reranker-on')")
    overrides: dict[str, str] = Field(
        default_factory=dict,
        description="Config key=value overrides to apply",
    )


class TuningComparison(BaseModel):
    """Result of one config compared against baseline."""

    config_name: str
    overrides: dict[str, str] = Field(default_factory=dict)
    metrics: RetrievalMetrics
    delta_mrr: float = Field(..., description="MRR@10 minus baseline")
    delta_recall: float = Field(..., description="Recall@10 minus baseline")
    delta_ndcg: float = Field(..., description="NDCG@10 minus baseline")
    delta_precision: float = Field(..., description="Precision@10 minus baseline")


class TuningReport(BaseModel):
    """Complete tuning experiment report."""

    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    baseline: RetrievalMetrics
    comparisons: list[TuningComparison] = Field(default_factory=list)
    best_config: str = Field(..., description="Config name with best overall improvement")
    recommendation: str = Field(..., description="Human-readable tuning recommendation")
