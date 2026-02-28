"""Pydantic schemas for the case intelligence layer.

API response/request models and Instructor extraction models for the
Case Setup Agent.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.common.models import CaseStatus, PartyRole

# ---------------------------------------------------------------------------
# API response / request schemas
# ---------------------------------------------------------------------------


class CaseSetupResponse(BaseModel):
    """Returned from POST /cases/{matter_id}/setup."""

    job_id: str
    case_context_id: str
    status: CaseStatus
    created_at: datetime


class ClaimResponse(BaseModel):
    """A single extracted claim / cause of action."""

    id: UUID
    claim_number: int
    claim_label: str
    claim_text: str
    legal_elements: list[str] = Field(default_factory=list)
    source_pages: list[int] = Field(default_factory=list)


class PartyResponse(BaseModel):
    """A party identified in the case."""

    id: UUID
    name: str
    role: PartyRole
    description: str | None = None
    aliases: list[str] = Field(default_factory=list)
    entity_id: str | None = None
    source_pages: list[int] = Field(default_factory=list)


class DefinedTermResponse(BaseModel):
    """A defined term extracted from the complaint."""

    id: UUID
    term: str
    definition: str
    entity_id: str | None = None
    source_pages: list[int] = Field(default_factory=list)


class TimelineEvent(BaseModel):
    """A single chronological event from the case timeline."""

    date: str
    event_text: str
    source_page: int | None = None


class CaseContextResponse(BaseModel):
    """Full case context with all extracted intelligence."""

    id: UUID
    matter_id: UUID
    status: CaseStatus
    anchor_document_id: str
    claims: list[ClaimResponse] = Field(default_factory=list)
    parties: list[PartyResponse] = Field(default_factory=list)
    defined_terms: list[DefinedTermResponse] = Field(default_factory=list)
    timeline: list[TimelineEvent] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ClaimInput(BaseModel):
    """Claim data for PATCH updates."""

    claim_number: int
    claim_label: str
    claim_text: str
    legal_elements: list[str] = Field(default_factory=list)
    source_pages: list[int] = Field(default_factory=list)


class PartyInput(BaseModel):
    """Party data for PATCH updates."""

    name: str
    role: PartyRole
    description: str | None = None
    aliases: list[str] = Field(default_factory=list)
    entity_id: str | None = None
    source_pages: list[int] = Field(default_factory=list)


class DefinedTermInput(BaseModel):
    """Defined term data for PATCH updates."""

    term: str
    definition: str
    entity_id: str | None = None
    source_pages: list[int] = Field(default_factory=list)


class CaseContextUpdateRequest(BaseModel):
    """PATCH body for editing extracted case context."""

    status: CaseStatus | None = None
    claims: list[ClaimInput] | None = None
    parties: list[PartyInput] | None = None
    defined_terms: list[DefinedTermInput] | None = None
    timeline: list[TimelineEvent] | None = None


class InvestigationSessionResponse(BaseModel):
    """An investigation session."""

    id: UUID
    matter_id: UUID
    case_context_id: UUID | None = None
    title: str | None = None
    findings: list[dict] = Field(default_factory=list)
    status: str = "active"
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Instructor extraction models (used by Case Setup Agent nodes)
# ---------------------------------------------------------------------------


class ExtractedClaim(BaseModel):
    """A single claim extracted by the LLM."""

    claim_number: int = Field(description="Sequential claim number (1, 2, 3, ...)")
    claim_label: str = Field(description="Short label, e.g. 'Fraud', 'Breach of Contract'")
    claim_text: str = Field(description="Full text of the claim or cause of action")
    legal_elements: list[str] = Field(
        default_factory=list,
        description="Key legal elements that must be proven for this claim",
    )
    source_pages: list[int] = Field(
        default_factory=list,
        description="Page numbers where this claim appears",
    )


class ExtractedClaimList(BaseModel):
    """Container for extracted claims."""

    claims: list[ExtractedClaim] = Field(default_factory=list)


class ExtractedParty(BaseModel):
    """A single party extracted by the LLM."""

    name: str = Field(description="Full legal name of the party")
    role: str = Field(description="One of: plaintiff, defendant, third_party, witness, counsel")
    description: str | None = Field(
        default=None,
        description="Brief description of the party's role in the case",
    )
    aliases: list[str] = Field(
        default_factory=list,
        description="Alternative names, abbreviations, or references used in the document",
    )
    source_pages: list[int] = Field(
        default_factory=list,
        description="Page numbers where this party is mentioned",
    )


class ExtractedPartyList(BaseModel):
    """Container for extracted parties."""

    parties: list[ExtractedParty] = Field(default_factory=list)


class ExtractedDefinedTerm(BaseModel):
    """A defined term extracted by the LLM."""

    term: str = Field(description="The defined term as it appears in the document")
    definition: str = Field(description="The definition or meaning of the term")
    source_pages: list[int] = Field(
        default_factory=list,
        description="Page numbers where this term is defined",
    )


class ExtractedDefinedTermList(BaseModel):
    """Container for extracted defined terms."""

    terms: list[ExtractedDefinedTerm] = Field(default_factory=list)


class ExtractedTimelineEvent(BaseModel):
    """A chronological event extracted by the LLM."""

    date: str = Field(description="Date or date range (e.g. 'March 2020', '2019-2021')")
    event_text: str = Field(description="Description of the event")
    source_page: int | None = Field(
        default=None,
        description="Page number where this event is mentioned",
    )


class ExtractedTimeline(BaseModel):
    """Container for extracted timeline events."""

    events: list[ExtractedTimelineEvent] = Field(default_factory=list)
