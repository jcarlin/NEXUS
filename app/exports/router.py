"""Export management API endpoints.

POST   /exports/production-sets                           -- create production set
GET    /exports/production-sets                           -- list production sets
GET    /exports/production-sets/{ps_id}                   -- get production set
POST   /exports/production-sets/{ps_id}/documents         -- add documents
GET    /exports/production-sets/{ps_id}/documents         -- list documents
DELETE /exports/production-sets/{ps_id}/documents/{doc_id} -- remove document
POST   /exports/production-sets/{ps_id}/assign-bates      -- assign Bates numbers

POST   /exports                      -- create export job (kicks Celery task)
GET    /exports/jobs                  -- list export jobs
GET    /exports/jobs/{job_id}         -- get export job status
GET    /exports/jobs/{job_id}/download -- download export file (streamed bytes)
GET    /exports/privilege-log/preview -- privilege log JSON preview
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.middleware import get_matter_id, require_role
from app.auth.schemas import UserRecord
from app.common.storage import StorageClient
from app.dependencies import get_db, get_minio
from app.exports.schemas import (
    ExportJobListResponse,
    ExportJobResponse,
    ExportRequest,
    PrivilegeLogEntry,
    PrivilegeLogPreviewResponse,
    ProductionSetAddDocuments,
    ProductionSetCreate,
    ProductionSetDocumentListResponse,
    ProductionSetDocumentResponse,
    ProductionSetListResponse,
    ProductionSetResponse,
)
from app.exports.service import ExportService

router = APIRouter(prefix="/exports", tags=["exports"])


# -----------------------------------------------------------------------
# Production Sets
# -----------------------------------------------------------------------


@router.post(
    "/production-sets",
    response_model=ProductionSetResponse,
    status_code=201,
)
async def create_production_set(
    body: ProductionSetCreate,
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(require_role("admin", "attorney", "paralegal")),
    matter_id: UUID = Depends(get_matter_id),
):
    """Create a new production set."""
    row = await ExportService.create_production_set(
        db=db,
        matter_id=matter_id,
        user_id=current_user.id,
        data=body.model_dump(),
    )
    return ProductionSetResponse(**row)


@router.get("/production-sets", response_model=ProductionSetListResponse)
async def list_production_sets(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(require_role("admin", "attorney", "paralegal")),
    matter_id: UUID = Depends(get_matter_id),
):
    """List all production sets for the current matter."""
    items, total = await ExportService.list_production_sets(
        db=db,
        matter_id=matter_id,
        offset=offset,
        limit=limit,
    )
    return ProductionSetListResponse(
        items=[ProductionSetResponse(**r) for r in items],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get("/production-sets/{ps_id}", response_model=ProductionSetResponse)
async def get_production_set(
    ps_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(require_role("admin", "attorney", "paralegal")),
    matter_id: UUID = Depends(get_matter_id),
):
    """Get a single production set by id."""
    row = await ExportService.get_production_set(db=db, ps_id=ps_id, matter_id=matter_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Production set {ps_id} not found")
    return ProductionSetResponse(**row)


@router.post(
    "/production-sets/{ps_id}/documents",
    response_model=list[ProductionSetDocumentResponse],
)
async def add_documents_to_production_set(
    ps_id: UUID,
    body: ProductionSetAddDocuments,
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(require_role("admin", "attorney", "paralegal")),
    matter_id: UUID = Depends(get_matter_id),
):
    """Add documents to a production set."""
    try:
        added = await ExportService.add_documents_to_production_set(
            db=db,
            ps_id=ps_id,
            matter_id=matter_id,
            doc_ids=body.document_ids,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return [ProductionSetDocumentResponse(**r) for r in added]


@router.get(
    "/production-sets/{ps_id}/documents",
    response_model=ProductionSetDocumentListResponse,
)
async def list_production_set_documents(
    ps_id: UUID,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(require_role("admin", "attorney", "paralegal")),
    matter_id: UUID = Depends(get_matter_id),
):
    """List documents in a production set."""
    try:
        items, total = await ExportService.list_production_set_documents(
            db=db,
            ps_id=ps_id,
            matter_id=matter_id,
            offset=offset,
            limit=limit,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return ProductionSetDocumentListResponse(
        items=[ProductionSetDocumentResponse(**r) for r in items],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.delete(
    "/production-sets/{ps_id}/documents/{doc_id}",
    status_code=204,
)
async def remove_document_from_production_set(
    ps_id: UUID,
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(require_role("admin", "attorney", "paralegal")),
    matter_id: UUID = Depends(get_matter_id),
):
    """Remove a document from a production set."""
    try:
        deleted = await ExportService.remove_document_from_production_set(
            db=db,
            ps_id=ps_id,
            doc_id=doc_id,
            matter_id=matter_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not deleted:
        raise HTTPException(status_code=404, detail="Document not found in production set")
    return Response(status_code=204)


@router.post(
    "/production-sets/{ps_id}/assign-bates",
    response_model=ProductionSetResponse,
)
async def assign_bates_numbers(
    ps_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(require_role("admin", "attorney", "paralegal")),
    matter_id: UUID = Depends(get_matter_id),
):
    """Assign sequential Bates numbers to all documents in a production set."""
    try:
        ps = await ExportService.assign_bates_numbers(
            db=db,
            ps_id=ps_id,
            matter_id=matter_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ProductionSetResponse(**ps)


# -----------------------------------------------------------------------
# Export Jobs
# -----------------------------------------------------------------------


@router.post("", response_model=ExportJobResponse, status_code=202)
async def create_export_job(
    body: ExportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(require_role("admin", "attorney", "paralegal")),
    matter_id: UUID = Depends(get_matter_id),
):
    """Create an export job and kick off the Celery task."""
    data = body.model_dump(mode="json")
    if body.document_ids:
        data["document_ids"] = [str(d) for d in body.document_ids]
    if body.production_set_id:
        data["production_set_id"] = str(body.production_set_id)

    job = await ExportService.create_export_job(
        db=db,
        matter_id=matter_id,
        user_id=current_user.id,
        data=data,
    )

    # Kick Celery task (import here to avoid circular imports at module level)
    from app.exports.tasks import run_export

    run_export.delay(str(job["id"]))

    return ExportJobResponse(**job)


@router.get("/jobs", response_model=ExportJobListResponse)
async def list_export_jobs(
    export_type: str | None = Query(None),
    status: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(require_role("admin", "attorney", "paralegal")),
    matter_id: UUID = Depends(get_matter_id),
):
    """List export jobs for the current matter."""
    items, total = await ExportService.list_export_jobs(
        db=db,
        matter_id=matter_id,
        export_type=export_type,
        status=status,
        offset=offset,
        limit=limit,
    )
    return ExportJobListResponse(
        items=[ExportJobResponse(**r) for r in items],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get("/jobs/{job_id}", response_model=ExportJobResponse)
async def get_export_job(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(require_role("admin", "attorney", "paralegal")),
    matter_id: UUID = Depends(get_matter_id),
):
    """Get the status of an export job."""
    row = await ExportService.get_export_job(db=db, job_id=job_id, matter_id=matter_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Export job {job_id} not found")
    return ExportJobResponse(**row)


@router.get("/jobs/{job_id}/download")
async def download_export(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(require_role("admin", "attorney", "paralegal")),
    matter_id: UUID = Depends(get_matter_id),
    storage: StorageClient = Depends(get_minio),
):
    """Get a presigned download URL for a completed export."""
    row = await ExportService.get_export_job(db=db, job_id=job_id, matter_id=matter_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Export job {job_id} not found")
    if row["status"] != "complete":
        raise HTTPException(status_code=400, detail="Export is not yet complete")
    if not row.get("output_path"):
        raise HTTPException(status_code=404, detail="Export output not available")

    data = await storage.download_bytes(row["output_path"])
    filename = row["output_path"].rsplit("/", 1)[-1]
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# -----------------------------------------------------------------------
# Privilege Log Preview
# -----------------------------------------------------------------------


@router.get("/privilege-log/preview", response_model=PrivilegeLogPreviewResponse)
async def privilege_log_preview(
    production_set_id: UUID | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(require_role("admin", "attorney", "paralegal")),
    matter_id: UUID = Depends(get_matter_id),
):
    """Preview the privilege log as JSON."""
    entries, total = await ExportService.get_privilege_log_preview(
        db=db,
        matter_id=matter_id,
        production_set_id=production_set_id,
        limit=limit,
    )
    return PrivilegeLogPreviewResponse(
        entries=[PrivilegeLogEntry(**e) for e in entries],
        total=total,
    )
