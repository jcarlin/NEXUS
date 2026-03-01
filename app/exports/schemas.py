"""Pydantic schemas for the exports domain."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field

from app.common.models import PaginatedResponse

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ExportType(StrEnum):
    COURT_READY = "court_ready"
    EDRM_XML = "edrm_xml"
    PRIVILEGE_LOG = "privilege_log"
    RESULT_SET = "result_set"


class ExportFormat(StrEnum):
    ZIP = "zip"
    CSV = "csv"
    XLSX = "xlsx"


class ExportStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETE = "complete"
    FAILED = "failed"


class ProductionSetStatus(StrEnum):
    DRAFT = "draft"
    FINALIZED = "finalized"
    EXPORTED = "exported"


class BatesMode(StrEnum):
    AUTO = "auto"
    PREFIX_START = "prefix_start"
    IMPORTED = "imported"


# ---------------------------------------------------------------------------
# Production Set request/response schemas
# ---------------------------------------------------------------------------


class ProductionSetCreate(BaseModel):
    name: str = Field(..., max_length=255)
    description: str | None = None
    bates_prefix: str = Field(default="NEXUS", max_length=50)
    bates_start: int = Field(default=1, ge=1)
    bates_padding: int = Field(default=6, ge=1, le=10)


class ProductionSetResponse(BaseModel):
    id: UUID
    matter_id: UUID
    name: str
    description: str | None
    bates_prefix: str
    bates_start: int
    bates_padding: int
    next_bates: int
    status: str
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    document_count: int = 0


class ProductionSetListResponse(PaginatedResponse[ProductionSetResponse]):
    pass


class ProductionSetAddDocuments(BaseModel):
    document_ids: list[UUID] = Field(..., min_length=1)


class ProductionSetDocumentResponse(BaseModel):
    id: UUID
    production_set_id: UUID
    document_id: UUID
    bates_begin: str | None
    bates_end: str | None
    filename: str | None = None
    added_at: datetime


class ProductionSetDocumentListResponse(PaginatedResponse[ProductionSetDocumentResponse]):
    pass


# ---------------------------------------------------------------------------
# Export Job request/response schemas
# ---------------------------------------------------------------------------


class ExportRequest(BaseModel):
    export_type: ExportType
    export_format: ExportFormat = ExportFormat.ZIP
    document_ids: list[UUID] | None = None  # None = all docs in matter
    production_set_id: UUID | None = None
    parameters: dict = Field(default_factory=dict)


class ExportJobResponse(BaseModel):
    id: UUID
    matter_id: UUID
    export_type: str
    export_format: str
    status: str
    parameters: dict
    output_path: str | None
    file_size_bytes: int | None
    error: str | None
    created_by: UUID
    created_at: datetime
    completed_at: datetime | None


class ExportJobListResponse(PaginatedResponse[ExportJobResponse]):
    pass


# ---------------------------------------------------------------------------
# Privilege Log preview
# ---------------------------------------------------------------------------


class PrivilegeLogEntry(BaseModel):
    bates_begin: str | None
    bates_end: str | None
    filename: str
    doc_type: str | None
    date: datetime | None
    privilege_status: str
    privilege_basis: str
    reviewed_by: str | None
    reviewed_at: datetime | None


class PrivilegeLogPreviewResponse(BaseModel):
    entries: list[PrivilegeLogEntry]
    total: int
