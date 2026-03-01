"""Pydantic schemas for the redaction domain."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field

from app.common.models import PaginatedResponse


class RedactionType(StrEnum):
    """How the redaction was initiated."""

    PII = "pii"
    PRIVILEGE = "privilege"
    MANUAL = "manual"


class PIICategory(StrEnum):
    """Categories of personally identifiable information."""

    SSN = "ssn"
    PHONE = "phone"
    EMAIL = "email"
    DOB = "dob"
    MEDICAL = "medical"


class PIIDetection(BaseModel):
    """A single PII instance detected in document text."""

    text: str
    category: PIICategory
    confidence: float = Field(ge=0.0, le=1.0)
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    chunk_index: int | None = None
    page_number: int | None = None


class RedactionSpec(BaseModel):
    """A single redaction to apply to a document."""

    page_number: int | None = None
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    reason: str
    redaction_type: RedactionType = RedactionType.MANUAL
    pii_category: PIICategory | None = None


class RedactRequest(BaseModel):
    """Request body for POST /documents/{document_id}/redact."""

    redactions: list[RedactionSpec] = Field(min_length=1)


class RedactResponse(BaseModel):
    """Result summary after applying redactions."""

    document_id: UUID
    matter_id: UUID
    redaction_count: int
    redacted_pdf_path: str


class RedactionLogEntry(BaseModel):
    """Immutable audit record for a single redaction."""

    id: UUID
    document_id: UUID
    matter_id: UUID
    user_id: UUID
    redaction_type: str
    pii_category: str | None = None
    page_number: int | None = None
    reason: str
    original_text_hash: str
    created_at: datetime


class RedactionLogResponse(PaginatedResponse[RedactionLogEntry]):
    """Paginated list of redaction log entries."""
