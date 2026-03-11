"""Shared base models and enums used across all NEXUS domains."""

from datetime import datetime
from enum import StrEnum
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class JobStatus(StrEnum):
    """Valid statuses for background jobs in the ``jobs`` table."""

    PENDING = "pending"
    PROCESSING = "processing"
    UPLOADING = "uploading"
    PARSING = "parsing"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    EXTRACTING = "extracting"
    INDEXING = "indexing"
    COMPLETE = "complete"
    FAILED = "failed"


class TaskType(StrEnum):
    """Discriminator for background job types tracked in the jobs table."""

    INGESTION = "ingestion"
    ENTITY_RESOLUTION = "entity_resolution"
    REPROCESS_NEO4J = "reprocess_neo4j"
    ANALYSIS_SENTIMENT = "analysis_sentiment"
    ANALYSIS_MATTER_SCAN = "analysis_matter_scan"
    CASE_SETUP = "case_setup"


class PrivilegeStatus(StrEnum):
    """Attorney-client privilege classification for documents."""

    PRIVILEGED = "privileged"
    WORK_PRODUCT = "work_product"
    CONFIDENTIAL = "confidential"
    NOT_PRIVILEGED = "not_privileged"


class CaseStatus(StrEnum):
    """Status of a case context through its lifecycle."""

    PROCESSING = "processing"
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    FAILED = "failed"


class PartyRole(StrEnum):
    """Role of a party in a legal case."""

    PLAINTIFF = "plaintiff"
    DEFENDANT = "defendant"
    THIRD_PARTY = "third_party"
    WITNESS = "witness"
    COUNSEL = "counsel"


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
