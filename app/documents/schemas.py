"""Pydantic schemas for the documents domain."""

from datetime import datetime
from enum import StrEnum
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
    summary: str | None = None


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


class DocumentHealthItem(BaseModel):
    """Health status for a single document's vector index."""

    doc_id: UUID
    filename: str
    expected_chunks: int
    indexed_chunks: int
    status: str  # "healthy" | "missing" | "partial"


class DocumentHealthResponse(BaseModel):
    """Aggregated health check results for document vector indexes."""

    total: int
    healthy: int
    missing: int
    partial: int
    documents: list[DocumentHealthItem]


class PrivilegeUpdateRequest(BaseModel):
    """Request body for updating a document's privilege status."""

    privilege_status: PrivilegeStatus


class PrivilegeUpdateResponse(BaseModel):
    """Response after updating privilege status."""

    id: UUID
    privilege_status: str
    privilege_reviewed_by: UUID
    privilege_reviewed_at: datetime


# ---------------------------------------------------------------------------
# Privilege Log schemas
# ---------------------------------------------------------------------------


class PrivilegeLogExportFormat(StrEnum):
    """Supported export formats for privilege logs."""

    CSV = "csv"
    XLSX = "xlsx"


class PrivilegeLogEntry(BaseModel):
    """A single entry in a court-formatted privilege log."""

    bates_number: str | None = None
    doc_date: str | None = None
    author: str | None = None
    recipients: str | None = None
    doc_type: str | None = None
    subject: str | None = None
    privilege_claimed: str | None = None
    basis: str | None = None


class PrivilegeLogResponse(BaseModel):
    """Response for the privilege log endpoint."""

    entries: list[PrivilegeLogEntry]
    total: int
    matter_id: UUID


class PrivilegeBasisUpdate(BaseModel):
    """Request body for updating privilege basis and exclusion."""

    privilege_basis: str | None = None
    privilege_log_excluded: bool = False


# ---------------------------------------------------------------------------
# Document Comparison / Redline schemas (T3-4)
# ---------------------------------------------------------------------------


class DiffOp(StrEnum):
    """Operation type for a diff block."""

    equal = "equal"
    insert = "insert"
    delete = "delete"
    replace = "replace"


class DiffBlock(BaseModel):
    """A single diff block between two document texts."""

    op: DiffOp
    left_start: int | None = None
    left_end: int | None = None
    right_start: int | None = None
    right_end: int | None = None
    left_text: str = ""
    right_text: str = ""


class DocumentDiffResponse(BaseModel):
    """Response for the document comparison endpoint."""

    left_id: UUID
    right_id: UUID
    left_filename: str
    right_filename: str
    blocks: list[DiffBlock]
    truncated: bool = False


class VersionGroupMember(BaseModel):
    """A single document within a version group."""

    id: UUID
    filename: str
    version_number: int | None = None
    is_final_version: bool | None = None
    created_at: datetime


class VersionGroupResponse(BaseModel):
    """Response listing all documents in a version group."""

    version_group_id: str
    members: list[VersionGroupMember]
