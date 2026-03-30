"""Pydantic schemas for the ingestion domain."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field

from app.common.models import JobStatus, PaginatedResponse


class ErrorCategory(StrEnum):
    """Auto-classified error categories for failed pipeline jobs."""

    TIMEOUT = "TIMEOUT"
    OOM = "OOM"
    PARSE_ERROR = "PARSE_ERROR"
    NETWORK = "NETWORK"
    LLM_API = "LLM_API"
    VALIDATION = "VALIDATION"
    STORAGE = "STORAGE"
    UNKNOWN = "UNKNOWN"


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
    error_category: str | None = None
    retry_count: int = 0
    worker_hostname: str | None = None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    file_size_bytes: int | None = None
    page_count: int | None = None
    document_type: str | None = None


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
    total_size_bytes: int = 0
    total_pages: int = 0


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


# ---------------------------------------------------------------------------
# Pipeline monitoring schemas
# ---------------------------------------------------------------------------


class TaskTypeThroughput(BaseModel):
    """Per-task-type throughput breakdown."""

    task_type: str
    jobs_per_minute: float = 0.0
    jobs_last_hour: int = 0


class PipelineThroughputResponse(BaseModel):
    """Throughput metrics for the pipeline health strip."""

    jobs_per_minute: float = 0.0
    jobs_last_hour: int = 0
    avg_duration_seconds: float = 0.0
    by_type: list[TaskTypeThroughput] = []


class ErrorCategoryBreakdown(BaseModel):
    """Single row in error category breakdown."""

    category: str
    count: int


class FailureRatePoint(BaseModel):
    """Single data point in the failure rate timeline."""

    timestamp: datetime
    completed: int
    failed: int


class TopError(BaseModel):
    """Deduplicated error entry with count."""

    error_summary: str
    category: str | None
    count: int
    last_seen: datetime


class StageFailure(BaseModel):
    """Stage failure count for distribution chart."""

    stage: str
    count: int


class FailureAnalysisResponse(BaseModel):
    """Aggregate failure analysis for the Health tab."""

    category_breakdown: list[ErrorCategoryBreakdown]
    failure_rate: list[FailureRatePoint]
    top_errors: list[TopError]
    stage_distribution: list[StageFailure]
    total_failed: int
    total_completed: int


# ---------------------------------------------------------------------------
# Pipeline events schemas
# ---------------------------------------------------------------------------


class PipelineEventResponse(BaseModel):
    """Single pipeline lifecycle event."""

    id: UUID
    job_id: UUID | None
    event_type: str
    timestamp: datetime
    worker: str | None
    detail: dict = Field(default_factory=dict)
    duration_ms: int | None = None
    filename: str | None = None


class PipelineEventListResponse(PaginatedResponse[PipelineEventResponse]):
    """Paginated list of pipeline events."""
