"""Pydantic v2 schemas for sentiment analysis and hot document detection."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class SentimentDimensions(BaseModel):
    """7-dimension sentiment scoring per Fraud Triangle theory."""

    positive: float = Field(default=0.0, ge=0.0, le=1.0)
    negative: float = Field(default=0.0, ge=0.0, le=1.0)
    pressure: float = Field(default=0.0, ge=0.0, le=1.0)
    opportunity: float = Field(default=0.0, ge=0.0, le=1.0)
    rationalization: float = Field(default=0.0, ge=0.0, le=1.0)
    intent: float = Field(default=0.0, ge=0.0, le=1.0)
    concealment: float = Field(default=0.0, ge=0.0, le=1.0)


class HotDocSignals(BaseModel):
    """Supplementary signals for hot document detection."""

    admission_guilt: float = Field(default=0.0, ge=0.0, le=1.0)
    inappropriate_enthusiasm: float = Field(default=0.0, ge=0.0, le=1.0)
    deliberate_vagueness: float = Field(default=0.0, ge=0.0, le=1.0)


class DocumentSentimentResult(BaseModel):
    """LLM response model for document sentiment scoring."""

    sentiment: SentimentDimensions
    signals: HotDocSignals
    hot_doc_score: float = Field(ge=0.0, le=1.0)
    summary: str = Field(description="Brief explanation of key findings")


class ContextGapType(StrEnum):
    missing_attachment = "missing_attachment"
    prior_conversation = "prior_conversation"
    forward_reference = "forward_reference"
    coded_language = "coded_language"
    unusual_terseness = "unusual_terseness"


class ContextGap(BaseModel):
    gap_type: ContextGapType
    evidence: str = Field(description="Quote or indicator supporting the gap detection")
    severity: float = Field(ge=0.0, le=1.0)


class CompletenessResult(BaseModel):
    """LLM response model for completeness analysis."""

    context_gap_score: float = Field(ge=0.0, le=1.0)
    gaps: list[ContextGap] = Field(default_factory=list)
    summary: str = Field(description="Brief summary of completeness findings")


class PersonBaseline(BaseModel):
    """Statistical baseline for a person's communication patterns."""

    avg_message_length: float = 0.0
    message_count: int = 0
    tone_profile: dict[str, float] = Field(default_factory=dict)


class AnomalyResult(BaseModel):
    """Result of anomaly detection against a person's baseline."""

    anomaly_score: float = Field(ge=0.0, le=1.0)
    deviations: dict[str, float] = Field(default_factory=dict)
