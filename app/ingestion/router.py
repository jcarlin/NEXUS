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

from app.auth.middleware import get_current_user, get_matter_id
from app.auth.schemas import UserRecord
from app.common.models import JobStatus
from app.common.rate_limit import rate_limit_ingests
from app.common.storage import StorageClient
from app.dependencies import get_db, get_minio
from app.ingestion.schemas import (
    BatchIngestResponse,
    BulkImportListResponse,
    BulkImportStatusResponse,
    DryRunRequest,
    DryRunResponse,
    IngestResponse,
    JobListResponse,
    JobProgress,
    JobStatusResponse,
    PresignedUploadRequest,
    PresignedUploadResponse,
    ProcessUploadedRequest,
    ReindexRequest,
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
        filename=row.get("filename"),
        task_type=row.get("task_type", "ingestion"),
        label=row.get("label"),
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
    dataset_id: UUID | None = Query(default=None, description="Auto-assign ingested document to this dataset"),
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
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
        matter_id=matter_id,
        dataset_id=dataset_id,
    )

    # 4. Commit so the job row is visible to the Celery worker's sync connection
    await db.commit()

    # 5. Dispatch Celery task
    process_document.delay(str(job_row["id"]), minio_path)

    logger.info("ingest.task_dispatched", job_id=str(job_row["id"]))

    # 6. Return response
    return IngestResponse(
        job_id=job_row["id"],
        status=JobStatus.PENDING,
        filename=filename,
        created_at=job_row["created_at"],
    )


# -----------------------------------------------------------------------
# POST /ingest/batch — multi-file upload
# -----------------------------------------------------------------------


@router.post("/ingest/batch", response_model=BatchIngestResponse)
async def ingest_batch(
    files: list[UploadFile] = File(...),
    dataset_id: UUID | None = Query(default=None, description="Auto-assign ingested documents to this dataset"),
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
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
            matter_id=matter_id,
            dataset_id=dataset_id,
        )

        job_ids.append(job_row["id"])
        filenames.append(filename)

    if not job_ids:
        raise HTTPException(status_code=400, detail="All uploaded files were empty")

    # Commit all job rows so they are visible to the Celery worker's sync connection
    await db.commit()

    # Dispatch all tasks after commit
    for job_id_val, fname in zip(job_ids, filenames):
        minio_path = f"raw/{job_id_val}/{fname}"
        process_document.delay(str(job_id_val), minio_path)

        logger.info(
            "ingest.batch.file_dispatched",
            batch_id=str(batch_id),
            job_id=str(job_id_val),
            filename=fname,
        )

    return BatchIngestResponse(
        batch_id=batch_id,
        job_ids=job_ids,
        filenames=filenames,
        total_files=len(job_ids),
    )


# -----------------------------------------------------------------------
# POST /ingest/upload — multipart file upload (API-proxied)
# -----------------------------------------------------------------------


@router.post("/ingest/upload")
async def upload_file(
    file: UploadFile = File(...),
    current_user: UserRecord = Depends(get_current_user),
    storage: StorageClient = Depends(get_minio),
):
    """Upload a file directly through the API."""
    job_id = uuid4()
    object_key = f"raw/{job_id}/{file.filename}"
    data = await file.read()
    await storage.upload_bytes(key=object_key, data=data, content_type=file.content_type or "application/octet-stream")
    return {"object_key": object_key, "filename": file.filename}


# -----------------------------------------------------------------------
# POST /ingest/presigned-upload — presigned PUT URL for direct S3 upload
# -----------------------------------------------------------------------


@router.post("/ingest/presigned-upload", response_model=PresignedUploadResponse)
async def get_presigned_upload_url(
    request: PresignedUploadRequest,
    current_user: UserRecord = Depends(get_current_user),
) -> PresignedUploadResponse:
    """Generate a presigned PUT URL for direct S3 upload from the browser."""
    storage = get_minio()
    job_id = uuid4()
    object_key = f"raw/{job_id}/{request.filename}"
    upload_url = await storage.get_presigned_put_url(
        key=object_key,
        content_type=request.content_type,
    )
    return PresignedUploadResponse(
        upload_url=upload_url,
        object_key=object_key,
    )


# -----------------------------------------------------------------------
# POST /ingest/process-uploaded — trigger ingestion for presigned uploads
# -----------------------------------------------------------------------


@router.post("/ingest/process-uploaded", response_model=BatchIngestResponse)
async def process_uploaded(
    request: ProcessUploadedRequest,
    dataset_id: UUID | None = Query(default=None, description="Auto-assign to this dataset"),
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
    _rate_limit=Depends(rate_limit_ingests),
):
    """Trigger ingestion for files already uploaded to MinIO via presigned PUT.

    Accepts a list of ``{object_key, filename}`` pairs.  For each file,
    creates a job record and dispatches a ``process_document`` Celery task.
    """
    batch_id = uuid4()
    job_ids: list = []
    filenames: list[str] = []

    minio_paths: list[str] = []
    for f in request.files:
        job_id = uuid4()

        job_row = await IngestionService.create_job(
            db=db,
            filename=f.filename,
            minio_path=f.object_key,
            job_id=job_id,
            matter_id=matter_id,
            dataset_id=dataset_id,
        )

        job_ids.append(job_row["id"])
        filenames.append(f.filename)
        minio_paths.append(f.object_key)

    # Commit all job rows so they are visible to the Celery worker's sync connection
    await db.commit()

    for job_id_val, fname, mpath in zip(job_ids, filenames, minio_paths):
        process_document.delay(str(job_id_val), mpath)

        logger.info(
            "ingest.process_uploaded.dispatched",
            batch_id=str(batch_id),
            job_id=str(job_id_val),
            filename=fname,
            object_key=mpath,
        )

    return BatchIngestResponse(
        batch_id=batch_id,
        job_ids=job_ids,
        filenames=filenames,
        total_files=len(job_ids),
    )


# -----------------------------------------------------------------------
# POST /ingest/reindex — re-ingest documents by ID (uses real MinIO paths)
# -----------------------------------------------------------------------


@router.post("/ingest/reindex", response_model=BatchIngestResponse)
async def reindex_documents(
    request: ReindexRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
    _rate_limit=Depends(rate_limit_ingests),
):
    """Re-ingest existing documents by looking up their real MinIO paths.

    Unlike ``process_uploaded`` which requires the caller to supply MinIO
    object keys, this endpoint resolves paths from the documents table.
    """
    docs = await IngestionService.get_documents_for_reindex(db, request.doc_ids, matter_id)
    if not docs:
        raise HTTPException(status_code=404, detail="No matching documents found in this matter")

    batch_id = uuid4()
    job_ids: list[UUID] = []
    filenames: list[str] = []

    for doc in docs:
        job_id = uuid4()
        await IngestionService.create_job(
            db=db,
            filename=doc["filename"],
            minio_path=doc["minio_path"],
            job_id=job_id,
            matter_id=matter_id,
        )
        job_ids.append(job_id)
        filenames.append(doc["filename"])

    await db.commit()

    for job_id_val, doc in zip(job_ids, docs):
        process_document.delay(str(job_id_val), doc["minio_path"])
        logger.info(
            "ingest.reindex.dispatched",
            batch_id=str(batch_id),
            job_id=str(job_id_val),
            doc_id=str(doc["id"]),
            filename=doc["filename"],
        )

    return BatchIngestResponse(
        batch_id=batch_id,
        job_ids=job_ids,
        filenames=filenames,
        total_files=len(job_ids),
    )


# -----------------------------------------------------------------------
# GET /bulk-imports — list all bulk import jobs (matter-scoped)
# -----------------------------------------------------------------------


@router.get("/bulk-imports", response_model=BulkImportListResponse)
async def list_bulk_imports(
    offset: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=200, description="Max records to return"),
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
):
    """List all bulk import jobs for the current matter (paginated, newest first)."""
    items, total = await IngestionService.list_bulk_imports(
        db=db,
        matter_id=matter_id,
        offset=offset,
        limit=limit,
    )

    from datetime import UTC, datetime

    def _row_to_response(row: dict) -> BulkImportStatusResponse:
        now = datetime.now(UTC)
        created = row["created_at"]
        elapsed = (now - created).total_seconds() if created else None

        estimated_remaining = None
        if elapsed and row.get("total_documents") and row["processed_documents"] > 0:
            rate = row["processed_documents"] / elapsed
            remaining_docs = row["total_documents"] - row["processed_documents"] - row["failed_documents"]
            if rate > 0 and remaining_docs > 0:
                estimated_remaining = remaining_docs / rate

        return BulkImportStatusResponse(
            import_id=row["id"],
            status=row["status"],
            adapter_type=row.get("adapter_type"),
            total_documents=row.get("total_documents"),
            processed_documents=row["processed_documents"],
            failed_documents=row["failed_documents"],
            skipped_documents=row["skipped_documents"],
            elapsed_seconds=elapsed,
            estimated_remaining_seconds=estimated_remaining,
            error=row.get("error"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    return BulkImportListResponse(
        items=[_row_to_response(row) for row in items],
        total=total,
        offset=offset,
        limit=limit,
    )


# -----------------------------------------------------------------------
# POST /ingest/import/dry-run — estimate import results
# -----------------------------------------------------------------------


@router.post("/ingest/import/dry-run", response_model=DryRunResponse)
async def import_dry_run(
    request: DryRunRequest,
    _user: UserRecord = Depends(get_current_user),
) -> DryRunResponse:
    """Estimate import results without actually processing."""
    return IngestionService.estimate_import(request)


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
    object_keys: list[str] = []
    event_names: list[str] = []

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

        job_ids.append(str(job_row["id"]))
        object_keys.append(object_key)
        event_names.append(record.eventName)

    if not job_ids:
        raise HTTPException(
            status_code=400,
            detail="No actionable s3:ObjectCreated events found in payload",
        )

    # Commit all job rows so they are visible to the Celery worker's sync connection
    await db.commit()

    for jid, okey, ename in zip(job_ids, object_keys, event_names):
        process_document.delay(jid, okey)
        logger.info(
            "webhook.job_dispatched",
            job_id=jid,
            object_key=okey,
            event_name=ename,
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
    current_user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
):
    """Return status and progress for a specific ingestion job."""
    row = await IngestionService.get_job(db=db, job_id=job_id, matter_id=matter_id)
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
    status: str | None = Query(None, description="Filter by job status (e.g. processing, complete, failed)"),
    task_type: str | None = Query(None, description="Filter by task type (e.g. ingestion, entity_resolution)"),
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
):
    """List all background jobs (paginated, newest first).

    Without a ``task_type`` filter, returns jobs of all types.
    """
    items, total = await IngestionService.list_jobs(
        db=db, offset=offset, limit=limit, matter_id=matter_id, status=status, task_type=task_type
    )
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
    current_user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
):
    """Cancel a running ingestion job.

    Sets the job status to ``failed`` with error ``Cancelled by user``.
    Jobs that are already complete or failed are not modified.
    """
    # Verify the job exists first
    row = await IngestionService.get_job(db=db, job_id=job_id, matter_id=matter_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    cancelled = await IngestionService.cancel_job(db=db, job_id=job_id)
    if not cancelled:
        raise HTTPException(
            status_code=409,
            detail=f"Job {job_id} is already in a terminal state ({row['status']})",
        )

    return {"status": "cancelled", "job_id": str(job_id)}


# -----------------------------------------------------------------------
# GET /bulk-imports/{import_id} — bulk import job status
# -----------------------------------------------------------------------


@router.get("/bulk-imports/{import_id}", response_model=BulkImportStatusResponse)
async def get_bulk_import_status(
    import_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
):
    """Return status and progress for a bulk import job."""
    row = await IngestionService.get_bulk_import_job(db=db, import_id=import_id, matter_id=matter_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Bulk import job {import_id} not found")

    # Compute elapsed / estimated remaining
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    created = row["created_at"]
    elapsed = (now - created).total_seconds() if created else None

    estimated_remaining = None
    if elapsed and row.get("total_documents") and row["processed_documents"] > 0:
        rate = row["processed_documents"] / elapsed
        remaining_docs = row["total_documents"] - row["processed_documents"] - row["failed_documents"]
        if rate > 0 and remaining_docs > 0:
            estimated_remaining = remaining_docs / rate

    return BulkImportStatusResponse(
        import_id=row["id"],
        status=row["status"],
        adapter_type=row.get("adapter_type"),
        total_documents=row.get("total_documents"),
        processed_documents=row["processed_documents"],
        failed_documents=row["failed_documents"],
        skipped_documents=row["skipped_documents"],
        elapsed_seconds=elapsed,
        estimated_remaining_seconds=estimated_remaining,
        error=row.get("error"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
