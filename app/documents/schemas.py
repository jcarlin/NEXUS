"""Pydantic schemas for the documents domain."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.common.models import PaginatedResponse, PrivilegeStatus


class DocumentResponse(BaseModel):
    """Metadata for a single ingested document."""

    id: UUID
    filename: str
    type: str | None = None
    page_count: int = 0
    chunk_count: int = 0
    entity_count: int = 0
    created_at: datetime
    minio_path: str
    privilege_status: str | None = None
    thread_id: str | None = None
    is_inclusive: bool | None = None
    duplicate_cluster_id: str | None = None
    version_group_id: str | None = None
    hot_doc_score: float | None = None


class DocumentDetail(DocumentResponse):
    """Extended document metadata including storage details."""

    metadata_: dict = Field(default_factory=dict)
    file_size_bytes: int | None = None
    content_hash: str | None = None
    job_id: UUID | None = None
    updated_at: datetime | None = None
    privilege_reviewed_by: UUID | None = None
    privilege_reviewed_at: datetime | None = None
    message_id: str | None = None
    in_reply_to: str | None = None
    thread_position: int | None = None
    duplicate_score: float | None = None
    version_number: int | None = None
    is_final_version: bool | None = None
    sentiment_positive: float | None = None
    sentiment_negative: float | None = None
    sentiment_pressure: float | None = None
    sentiment_opportunity: float | None = None
    sentiment_rationalization: float | None = None
    sentiment_intent: float | None = None
    sentiment_concealment: float | None = None
    context_gap_score: float | None = None
    context_gaps: list[str] = Field(default_factory=list)
    anomaly_score: float | None = None
    bates_begin: str | None = None
    bates_end: str | None = None


class DocumentListResponse(PaginatedResponse[DocumentResponse]):
    """Paginated list of ingested documents."""


class PrivilegeUpdateRequest(BaseModel):
    """Request body for updating a document's privilege status."""

    privilege_status: PrivilegeStatus


class PrivilegeUpdateResponse(BaseModel):
    """Response after updating privilege status."""

    id: UUID
    privilege_status: str
    privilege_reviewed_by: UUID
    privilege_reviewed_at: datetime
