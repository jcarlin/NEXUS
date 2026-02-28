"""Pydantic schemas for the EDRM interop domain."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field

from app.common.models import PaginatedResponse


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class LoadFileFormat(StrEnum):
    """Supported EDRM load file formats."""

    CONCORDANCE_DAT = "concordance_dat"
    OPTICON_OPT = "opticon_opt"
    EDRM_XML = "edrm_xml"


class ImportStatus(StrEnum):
    """Status of an EDRM import job."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETE = "complete"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# Load file record schemas
# ---------------------------------------------------------------------------

class LoadFileRecord(BaseModel):
    """A single record parsed from an EDRM load file."""

    doc_id: str
    fields: dict[str, str] = Field(default_factory=dict)


class OpticonRecord(BaseModel):
    """A single record parsed from an Opticon OPT file."""

    doc_id: str
    volume: str = ""
    image_path: str = ""
    document_break: str = ""
    box_or_folder: str = ""
    pages: str = ""


# ---------------------------------------------------------------------------
# Import / export request/response schemas
# ---------------------------------------------------------------------------

class EDRMImportRequest(BaseModel):
    """Request body for importing an EDRM load file."""

    format: LoadFileFormat


class EDRMImportResponse(BaseModel):
    """Response after starting an EDRM import."""

    import_id: UUID
    status: ImportStatus
    record_count: int = 0
    message: str = ""


class EDRMExportRequest(BaseModel):
    """Request parameters for exporting documents as EDRM XML."""

    format: LoadFileFormat = LoadFileFormat.EDRM_XML


class EDRMImportLogEntry(BaseModel):
    """An entry from the edrm_import_log table."""

    id: UUID
    matter_id: UUID
    filename: str
    format: str
    record_count: int
    status: str
    error: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


class EDRMImportLogListResponse(PaginatedResponse[EDRMImportLogEntry]):
    """Paginated list of EDRM import log entries."""


# ---------------------------------------------------------------------------
# Thread / duplicate response schemas
# ---------------------------------------------------------------------------

class ThreadResponse(BaseModel):
    """Response for email thread listing."""

    thread_id: str
    message_count: int
    subject: str | None = None
    earliest: datetime | None = None
    latest: datetime | None = None


class ThreadListResponse(PaginatedResponse[ThreadResponse]):
    """Paginated list of email threads."""


class DuplicateCluster(BaseModel):
    """A cluster of near-duplicate documents."""

    cluster_id: str
    document_count: int
    avg_score: float | None = None


class DuplicateClusterListResponse(PaginatedResponse[DuplicateCluster]):
    """Paginated list of duplicate clusters."""
