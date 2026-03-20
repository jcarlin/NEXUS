"""Pydantic schemas for the ingestion domain."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.common.models import JobStatus, PaginatedResponse


class IngestResponse(BaseModel):
    """Returned when a file is accepted for ingestion."""

    job_id: UUID
    status: JobStatus = JobStatus.PENDING
    filename: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class JobProgress(BaseModel):
    """Breakdown of progress within an ingestion job."""

    stage: str = "uploading"
    pages_parsed: int = 0
    chunks_created: int = 0
    entities_extracted: int = 0
    embeddings_generated: int = 0


class JobStatusResponse(BaseModel):
    """Full status view of a background job (ingestion or other task types)."""

    job_id: UUID
    status: JobStatus
    stage: str = "uploading"
    filename: str | None = None
    task_type: str = "ingestion"
    label: str | None = None
    progress: JobProgress = Field(default_factory=JobProgress)
    error: str | None = None
    created_at: datetime
    updated_at: datetime


class JobListResponse(PaginatedResponse[JobStatusResponse]):
    """Paginated list of ingestion jobs."""


class BatchIngestResponse(BaseModel):
    """Returned when a batch of files is accepted for ingestion."""

    batch_id: UUID
    job_ids: list[UUID]
    filenames: list[str]
    total_files: int


# ---------------------------------------------------------------------------
# MinIO S3 Event Notification schemas
# ---------------------------------------------------------------------------


class S3EventRecord(BaseModel):
    """Single record from an S3/MinIO bucket event notification."""

    eventName: str = ""  # noqa: N815
    s3: dict = Field(default_factory=dict)


class S3EventNotification(BaseModel):
    """Payload sent by MinIO for bucket event notifications."""

    Records: list[S3EventRecord] = Field(default_factory=list)
    matter_id: UUID = Field(..., description="Matter ID to scope ingested documents")


class WebhookResponse(BaseModel):
    """Response from the MinIO webhook endpoint."""

    status: str
    job_ids: list[str]
    total: int


# ---------------------------------------------------------------------------
# Bulk import schemas
# ---------------------------------------------------------------------------


class BulkImportStatusResponse(BaseModel):
    """Status view of a bulk import job."""

    import_id: UUID
    status: str
    adapter_type: str | None = None
    source_path: str | None = None
    total_documents: int | None = None
    processed_documents: int = 0
    failed_documents: int = 0
    skipped_documents: int = 0
    elapsed_seconds: float | None = None
    estimated_remaining_seconds: float | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Dry-run schemas
# ---------------------------------------------------------------------------


class DryRunRequest(BaseModel):
    """Request body for estimating import results without processing."""

    source_type: str = Field(..., pattern="^(upload|s3|load_file)$")
    file_count: int | None = Field(None, ge=1)
    total_size_bytes: int | None = Field(None, ge=0)
    s3_prefix: str | None = None
    load_file_path: str | None = None


class DryRunResponse(BaseModel):
    """Estimated import results."""

    estimated_documents: int
    estimated_chunks: int
    estimated_duration_minutes: float
    estimated_storage_mb: float
    warnings: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Presigned upload schemas
# ---------------------------------------------------------------------------


class PresignedUploadRequest(BaseModel):
    """Request body for generating a presigned PUT URL."""

    filename: str = Field(..., min_length=1, max_length=500)
    content_type: str = Field(default="application/octet-stream")
    matter_id: UUID


class PresignedUploadResponse(BaseModel):
    """Presigned PUT URL and associated metadata."""

    upload_url: str
    object_key: str
    expires_in: int = 3600


# ---------------------------------------------------------------------------
# Process-uploaded schemas
# ---------------------------------------------------------------------------


class ProcessUploadedFile(BaseModel):
    """A single file already uploaded to MinIO via presigned PUT."""

    object_key: str = Field(..., min_length=1)
    filename: str = Field(..., min_length=1)


class ProcessUploadedRequest(BaseModel):
    """Request to trigger ingestion for files already in MinIO."""

    files: list[ProcessUploadedFile] = Field(..., min_length=1)


# ---------------------------------------------------------------------------
# Re-index schemas
# ---------------------------------------------------------------------------


class ReindexRequest(BaseModel):
    """Request to re-ingest documents by their DB IDs."""

    doc_ids: list[UUID] = Field(..., min_length=1, max_length=500)


# ---------------------------------------------------------------------------
# Bulk import list
# ---------------------------------------------------------------------------


class BulkImportListResponse(PaginatedResponse[BulkImportStatusResponse]):
    """Paginated list of bulk import jobs."""
