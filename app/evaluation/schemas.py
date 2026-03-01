"""Evaluation domain Pydantic schemas."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field

from app.common.models import PaginatedResponse


class DatasetType(StrEnum):
    GROUND_TRUTH = "ground_truth"
    ADVERSARIAL = "adversarial"
    LEGAL_BENCH = "legal_bench"


class EvalRunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class EvalMode(StrEnum):
    FULL = "full"
    QUICK = "quick"
    CUSTOM = "custom"


# --- Dataset Items ---


class DatasetItemCreate(BaseModel):
    question: str = Field(..., min_length=1)
    expected_answer: str = Field(..., min_length=1)
    tags: list[str] = Field(default_factory=list)
    metadata_: dict = Field(default_factory=dict)


class DatasetItemResponse(BaseModel):
    id: UUID
    dataset_type: DatasetType
    question: str
    expected_answer: str
    tags: list[str]
    metadata_: dict
    created_at: datetime


class DatasetItemListResponse(PaginatedResponse[DatasetItemResponse]):
    """Paginated list of dataset items."""


# --- Evaluation Runs ---


class RunCreateRequest(BaseModel):
    mode: EvalMode = EvalMode.FULL
    config_overrides: dict = Field(default_factory=dict)


class EvalMetrics(BaseModel):
    accuracy: float = 0.0
    faithfulness: float = 0.0
    relevance: float = 0.0
    citation_precision: float = 0.0
    citation_recall: float = 0.0
    latency_p50_ms: float = 0.0
    latency_p95_ms: float = 0.0


class EvalRunResponse(BaseModel):
    id: UUID
    mode: EvalMode
    status: EvalRunStatus
    metrics: EvalMetrics | None = None
    config_overrides: dict = Field(default_factory=dict)
    total_items: int = 0
    processed_items: int = 0
    error: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


class EvalRunListResponse(PaginatedResponse[EvalRunResponse]):
    """Paginated list of evaluation runs."""


class LatestEvalResponse(BaseModel):
    metrics: EvalMetrics
    passed: bool
    run_id: UUID
    completed_at: datetime | None = None
