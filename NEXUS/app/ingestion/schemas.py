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
    """Full status view of an ingestion job."""

    job_id: UUID
    status: JobStatus
    stage: str = "uploading"
    filename: str
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
