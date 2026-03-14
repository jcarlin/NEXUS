"""Pydantic schemas for the depositions domain."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class QuestionCategory(StrEnum):
    relationship = "relationship"
    timeline = "timeline"
    document_specific = "document_specific"
    inconsistency = "inconsistency"


class SuggestedQuestion(BaseModel):
    question: str
    category: QuestionCategory
    basis_document_ids: list[str] = Field(default_factory=list)
    rationale: str


class WitnessProfile(BaseModel):
    name: str
    entity_type: str = "person"
    document_count: int = 0
    connection_count: int = 0
    connected_entities: list[dict] = Field(default_factory=list)
    document_mentions: list[dict] = Field(default_factory=list)
    roles: list[str] = Field(default_factory=list)


class DepositionPrepRequest(BaseModel):
    witness_name: str = Field(..., min_length=1)
    max_questions: int = Field(default=15, ge=1, le=50)
    focus_categories: list[QuestionCategory] | None = None


class DepositionPrepResponse(BaseModel):
    witness: WitnessProfile
    questions: list[SuggestedQuestion]
    document_summaries: list[dict] = Field(default_factory=list)


class WitnessListResponse(BaseModel):
    witnesses: list[WitnessProfile]
    total: int
