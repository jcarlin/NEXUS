"""Shared base models and enums used across all NEXUS domains."""

from datetime import datetime
from enum import StrEnum
from typing import Generic, TypeVar

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class JobStatus(StrEnum):
    """Stages an ingestion job passes through (Section 5.1)."""

    PENDING = "pending"
    UPLOADING = "uploading"
    PARSING = "parsing"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    EXTRACTING = "extracting"
    INDEXING = "indexing"
    COMPLETE = "complete"
    FAILED = "failed"


class DocumentType(StrEnum):
    """Broad document categories for filtering and analytics."""

    DEPOSITION = "deposition"
    FLIGHT_LOG = "flight_log"
    CORRESPONDENCE = "correspondence"
    FINANCIAL = "financial"
    LEGAL_FILING = "legal_filing"
    EMAIL = "email"
    REPORT = "report"
    IMAGE = "image"
    OTHER = "other"


# ---------------------------------------------------------------------------
# Mixins / base schemas
# ---------------------------------------------------------------------------

class TimestampMixin(BaseModel):
    """Mixin that adds created_at / updated_at fields with sane defaults."""

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Generic paginated response
# ---------------------------------------------------------------------------

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """Envelope for paginated list endpoints."""

    items: list[T]
    total: int
    offset: int = 0
    limit: int = 50
