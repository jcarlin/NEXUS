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


class DocumentDetail(DocumentResponse):
    """Extended document metadata including storage details."""

    metadata_: dict = Field(default_factory=dict)
    file_size_bytes: int | None = None
    content_hash: str | None = None
    job_id: UUID | None = None
    updated_at: datetime | None = None
    privilege_reviewed_by: UUID | None = None
    privilege_reviewed_at: datetime | None = None


class DocumentListResponse(PaginatedResponse[DocumentResponse]):
    """Paginated list of ingested documents."""


class DocumentPreview(BaseModel):
    """Thumbnail / page-image reference for document preview."""

    doc_id: UUID
    page: int = Field(default=1, ge=1)
    image_url: str


class PrivilegeUpdateRequest(BaseModel):
    """Request body for updating a document's privilege status."""

    privilege_status: PrivilegeStatus


class PrivilegeUpdateResponse(BaseModel):
    """Response after updating privilege status."""

    id: UUID
    privilege_status: str
    privilege_reviewed_by: UUID
    privilege_reviewed_at: datetime
