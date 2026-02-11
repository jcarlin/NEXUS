"""Ingestion API endpoints.

POST /ingest          -- single file upload
POST /ingest/batch    -- multi-file upload (accepts ZIP)  [M3]
POST /ingest/webhook  -- MinIO bucket notification handler [M3]
GET  /jobs/{job_id}   -- job status + progress
GET  /jobs            -- list all jobs (paginated)
DELETE /jobs/{job_id} -- cancel running job
"""

from __future__ import annotations

from uuid import UUID, uuid4

import structlog
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.rate_limit import rate_limit_ingests
from app.dependencies import get_db, get_minio
from app.ingestion.schemas import (
    BatchIngestResponse,
    IngestResponse,
    JobListResponse,
    JobProgress,
    JobStatusResponse,
    S3EventNotification,
    WebhookResponse,
)
from app.ingestion.service import IngestionService
from app.ingestion.tasks import process_document

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["ingestion"])


# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------

def _job_row_to_status_response(row: dict) -> JobStatusResponse:
    """Convert a raw DB row dict into a ``JobStatusResponse``."""
    progress_raw = row.get("progress") or {}
    # Handle both string and dict progress values
    if isinstance(progress_raw, str):
        import json

        try:
            progress_raw = json.loads(progress_raw)
        except (json.JSONDecodeError, TypeError):
            progress_raw = {}

    return JobStatusResponse(
        job_id=row["id"],
        status=row["status"],
        stage=row.get("stage", "uploading"),
        filename=row["filename"],
        progress=JobProgress(
            stage=row.get("stage", "uploading"),
            pages_parsed=progress_raw.get("pages_parsed", 0),
            chunks_created=progress_raw.get("chunks_created", 0),
            entities_extracted=progress_raw.get("entities_extracted", 0),
            embeddings_generated=progress_raw.get("embeddings_generated", 0),
        ),
        error=row.get("error"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


# -----------------------------------------------------------------------
# POST /ingest — single file upload
# -----------------------------------------------------------------------

@router.post("/ingest", response_model=IngestResponse)
async def ingest_single(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _rate_limit=Depends(rate_limit_ingests),
):
    """Upload a single file for ingestion.

    1. Read file bytes from the upload.
    2. Store the original file in MinIO under ``raw/{job_id}/{filename}``.
    3. Create a job record in PostgreSQL.
    4. Dispatch the ``process_document`` Celery task.
    5. Return the job id so the client can poll for progress.
    """
    # 1. Read the uploaded file
    file_bytes = await file.read()
    filename = file.filename or "unnamed"

    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    # 2. Upload to MinIO
    storage = get_minio()
    job_id = uuid4()
    minio_path = f"raw/{job_id}/{filename}"

    content_type = file.content_type or "application/octet-stream"
    await storage.upload_bytes(key=minio_path, data=file_bytes, content_type=content_type)

    logger.info(
        "ingest.file_uploaded",
        job_id=str(job_id),
        filename=filename,
        size=len(file_bytes),
        minio_path=minio_path,
    )

    # 3. Create job record in Postgres (use the same job_id as the MinIO path)
    job_row = await IngestionService.create_job(
        db=db,
        filename=filename,
        minio_path=minio_path,
        job_id=job_id,
    )

    # 4. Dispatch Celery task
    process_document.delay(str(job_row["id"]), minio_path)

    logger.info("ingest.task_dispatched", job_id=str(job_row["id"]))

    # 5. Return response
    return IngestResponse(
        job_id=job_row["id"],
        status="pending",
        filename=filename,
        created_at=job_row["created_at"],
    )


# -----------------------------------------------------------------------
# POST /ingest/batch — multi-file upload
# -----------------------------------------------------------------------

@router.post("/ingest/batch", response_model=BatchIngestResponse)
async def ingest_batch(
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    _rate_limit=Depends(rate_limit_ingests),
):
    """Upload multiple files for ingestion.

    Each file is uploaded to MinIO, gets its own job record, and a separate
    Celery task is dispatched.  ZIP files are supported and handled by the
    ``process_zip`` task which extracts and dispatches child jobs.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    storage = get_minio()
    batch_id = uuid4()
    job_ids: list = []
    filenames: list[str] = []

    for file in files:
        file_bytes = await file.read()
        filename = file.filename or "unnamed"

        if len(file_bytes) == 0:
            logger.warning("ingest.batch.skipping_empty", filename=filename)
            continue

        job_id = uuid4()
        minio_path = f"raw/{job_id}/{filename}"

        content_type = file.content_type or "application/octet-stream"
        await storage.upload_bytes(key=minio_path, data=file_bytes, content_type=content_type)

        job_row = await IngestionService.create_job(
            db=db,
            filename=filename,
            minio_path=minio_path,
            job_id=job_id,
        )

        process_document.delay(str(job_row["id"]), minio_path)

        job_ids.append(job_row["id"])
        filenames.append(filename)

        logger.info(
            "ingest.batch.file_dispatched",
            batch_id=str(batch_id),
            job_id=str(job_row["id"]),
            filename=filename,
        )

    if not job_ids:
        raise HTTPException(status_code=400, detail="All uploaded files were empty")

    return BatchIngestResponse(
        batch_id=batch_id,
        job_ids=job_ids,
        filenames=filenames,
        total_files=len(job_ids),
    )


# -----------------------------------------------------------------------
# POST /ingest/webhook — MinIO bucket notification handler
# -----------------------------------------------------------------------

@router.post("/ingest/webhook", response_model=WebhookResponse)
async def ingest_webhook(
    payload: S3EventNotification,
    db: AsyncSession = Depends(get_db),
):
    """Receive MinIO bucket event notifications and trigger ingestion.

    Parses S3-style event records, filters for ``s3:ObjectCreated:*`` events,
    creates a job per object, and dispatches Celery tasks.
    """
    if not payload.Records:
        raise HTTPException(status_code=400, detail="No event records in payload")

    job_ids: list[str] = []

    for record in payload.Records:
        # Only process object-created events
        if not record.eventName.startswith("s3:ObjectCreated:"):
            continue

        # Extract the object key from the S3 event structure
        s3_info = record.s3
        obj = s3_info.get("object", {})
        object_key = obj.get("key", "")

        if not object_key:
            continue

        # Extract filename from the key
        filename = object_key.rsplit("/", 1)[-1] if "/" in object_key else object_key

        # Create job record
        job_row = await IngestionService.create_job(
            db=db,
            filename=filename,
            minio_path=object_key,
        )

        # Dispatch Celery task
        process_document.delay(str(job_row["id"]), object_key)

        job_ids.append(str(job_row["id"]))

        logger.info(
            "webhook.job_dispatched",
            job_id=str(job_row["id"]),
            object_key=object_key,
            event_name=record.eventName,
        )

    if not job_ids:
        raise HTTPException(
            status_code=400,
            detail="No actionable s3:ObjectCreated events found in payload",
        )

    return WebhookResponse(
        status="accepted",
        job_ids=job_ids,
        total=len(job_ids),
    )


# -----------------------------------------------------------------------
# GET /jobs/{job_id} — job status + progress
# -----------------------------------------------------------------------

@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Return status and progress for a specific ingestion job."""
    row = await IngestionService.get_job(db=db, job_id=job_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return _job_row_to_status_response(row)


# -----------------------------------------------------------------------
# GET /jobs — list all jobs (paginated)
# -----------------------------------------------------------------------

@router.get("/jobs", response_model=JobListResponse)
async def list_jobs(
    offset: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=200, description="Max records to return"),
    db: AsyncSession = Depends(get_db),
):
    """List all ingestion jobs (paginated, newest first)."""
    items, total = await IngestionService.list_jobs(db=db, offset=offset, limit=limit)
    return JobListResponse(
        items=[_job_row_to_status_response(row) for row in items],
        total=total,
        offset=offset,
        limit=limit,
    )


# -----------------------------------------------------------------------
# DELETE /jobs/{job_id} — cancel running job
# -----------------------------------------------------------------------

@router.delete("/jobs/{job_id}")
async def cancel_job(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Cancel a running ingestion job.

    Sets the job status to ``failed`` with error ``Cancelled by user``.
    Jobs that are already complete or failed are not modified.
    """
    # Verify the job exists first
    row = await IngestionService.get_job(db=db, job_id=job_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    cancelled = await IngestionService.cancel_job(db=db, job_id=job_id)
    if not cancelled:
        raise HTTPException(
            status_code=409,
            detail=f"Job {job_id} is already in a terminal state ({row['status']})",
        )

    return {"status": "cancelled", "job_id": str(job_id)}
