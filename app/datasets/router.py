"""Dataset and collection management API endpoints.

POST   /datasets                              — create folder
GET    /datasets                              — list (flat, paginated)
GET    /datasets/tree                         — full tree structure
GET    /datasets/{id}                         — single dataset + counts
PATCH  /datasets/{id}                         — update name/description/parent
DELETE /datasets/{id}                         — delete + cascade

POST   /datasets/{id}/documents               — assign documents
DELETE /datasets/{id}/documents               — unassign documents
POST   /datasets/{id}/documents/move          — move to another dataset
GET    /datasets/{id}/documents               — list documents in dataset

POST   /documents/{id}/tags                   — add tag
DELETE /documents/{id}/tags/{tag_name}        — remove tag
GET    /documents/{id}/tags                   — list tags on document
GET    /tags                                   — all tags in matter (autocomplete)
GET    /tags/{tag_name}/documents             — documents with tag

POST   /datasets/{id}/access                  — grant access
DELETE /datasets/{id}/access/{user_id}        — revoke access
GET    /datasets/{id}/access                  — list access entries
"""

from __future__ import annotations

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.middleware import get_current_user, get_matter_id, require_role
from app.auth.schemas import UserRecord
from app.datasets.schemas import (
    AssignDocumentsRequest,
    BulkImportStatusResponse,
    DatasetAccessRequest,
    DatasetAccessResponse,
    DatasetCreateRequest,
    DatasetIngestRequest,
    DatasetIngestResponse,
    DatasetListResponse,
    DatasetResponse,
    DatasetTreeResponse,
    DatasetUpdateRequest,
    DocumentTagsResponse,
    DryRunEstimate,
    MoveDocumentsRequest,
    TagRequest,
    TagResponse,
)
from app.datasets.service import DatasetService
from app.dependencies import get_db
from app.documents.router import _row_to_response
from app.documents.schemas import DocumentListResponse

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["datasets"])


# ------------------------------------------------------------------
# Dataset CRUD
# ------------------------------------------------------------------


@router.post("/datasets", response_model=DatasetResponse, status_code=201)
async def create_dataset(
    request: DatasetCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
) -> DatasetResponse:
    """Create a new dataset (folder) in the current matter."""
    try:
        result = await DatasetService.create_dataset(
            db,
            name=request.name,
            description=request.description,
            parent_id=request.parent_id,
            matter_id=matter_id,
            created_by=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    logger.info("dataset.created", dataset_id=str(result.id), matter_id=str(matter_id))
    return result


@router.get("/datasets", response_model=DatasetListResponse)
async def list_datasets(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
) -> DatasetListResponse:
    """List all datasets in the current matter (flat, paginated)."""
    items, total = await DatasetService.list_datasets(db, matter_id, offset, limit)
    return DatasetListResponse(items=items, total=total, offset=offset, limit=limit)


@router.get("/datasets/tree", response_model=DatasetTreeResponse)
async def get_dataset_tree(
    db: AsyncSession = Depends(get_db),
    _user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
) -> DatasetTreeResponse:
    """Return the full folder tree for the current matter."""
    roots, total = await DatasetService.get_dataset_tree(db, matter_id)
    return DatasetTreeResponse(roots=roots, total_datasets=total)


@router.get("/datasets/{dataset_id}", response_model=DatasetResponse)
async def get_dataset(
    dataset_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
) -> DatasetResponse:
    """Get a single dataset with document and children counts."""
    result = await DatasetService.get_dataset(db, dataset_id, matter_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return result


@router.patch("/datasets/{dataset_id}", response_model=DatasetResponse)
async def update_dataset(
    dataset_id: UUID,
    request: DatasetUpdateRequest,
    db: AsyncSession = Depends(get_db),
    _user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
) -> DatasetResponse:
    """Update a dataset's name, description, or parent (move)."""
    kwargs: dict = {}
    if request.name is not None:
        kwargs["name"] = request.name
    if request.description is not None:
        kwargs["description"] = request.description
    # Use sentinel to distinguish "not provided" from "set to null".
    update_data = request.model_dump(exclude_unset=True)
    if "parent_id" in update_data:
        kwargs["parent_id"] = request.parent_id

    try:
        result = await DatasetService.update_dataset(db, dataset_id, matter_id, **kwargs)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if result is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    await db.commit()
    return result


@router.delete("/datasets/{dataset_id}", status_code=204)
async def delete_dataset(
    dataset_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: UserRecord = Depends(require_role("admin", "attorney")),
    matter_id: UUID = Depends(get_matter_id),
):
    """Delete a dataset and cascade to children."""
    deleted = await DatasetService.delete_dataset(db, dataset_id, matter_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Dataset not found")
    await db.commit()


# ------------------------------------------------------------------
# Document assignment
# ------------------------------------------------------------------


@router.post("/datasets/{dataset_id}/documents", status_code=200)
async def assign_documents(
    dataset_id: UUID,
    request: AssignDocumentsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
):
    """Assign documents to a dataset."""
    try:
        count = await DatasetService.assign_documents(
            db,
            dataset_id,
            request.document_ids,
            matter_id,
            current_user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    await db.commit()
    return {"assigned": count}


@router.delete("/datasets/{dataset_id}/documents", status_code=200)
async def unassign_documents(
    dataset_id: UUID,
    request: AssignDocumentsRequest,
    db: AsyncSession = Depends(get_db),
    _user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
):
    """Remove documents from a dataset."""
    try:
        count = await DatasetService.unassign_documents(
            db,
            dataset_id,
            request.document_ids,
            matter_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    await db.commit()
    return {"unassigned": count}


@router.post("/datasets/{dataset_id}/documents/move", status_code=200)
async def move_documents(
    dataset_id: UUID,
    request: MoveDocumentsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
):
    """Move documents from this dataset to another."""
    try:
        count = await DatasetService.move_documents(
            db,
            dataset_id,
            request.target_dataset_id,
            request.document_ids,
            matter_id,
            current_user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    await db.commit()
    return {"moved": count}


@router.get(
    "/datasets/{dataset_id}/documents",
    response_model=DocumentListResponse,
)
async def list_dataset_documents(
    dataset_id: UUID,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
):
    """List documents assigned to a dataset."""
    try:
        items, total = await DatasetService.list_dataset_documents(
            db,
            dataset_id,
            matter_id,
            offset,
            limit,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return DocumentListResponse(
        items=[_row_to_response(row) for row in items],
        total=total,
        offset=offset,
        limit=limit,
    )


# ------------------------------------------------------------------
# Tags
# ------------------------------------------------------------------


@router.post("/documents/{document_id}/tags", status_code=201)
async def add_tag(
    document_id: UUID,
    request: TagRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
):
    """Add a tag to a document."""
    try:
        created = await DatasetService.add_tag(
            db,
            document_id,
            request.tag_name,
            matter_id,
            current_user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    await db.commit()
    return {"tag_name": request.tag_name, "created": created}


@router.delete("/documents/{document_id}/tags/{tag_name}", status_code=204)
async def remove_tag(
    document_id: UUID,
    tag_name: str,
    db: AsyncSession = Depends(get_db),
    _user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
):
    """Remove a tag from a document."""
    removed = await DatasetService.remove_tag(db, document_id, tag_name, matter_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Tag not found on document")
    await db.commit()


@router.get("/documents/{document_id}/tags", response_model=DocumentTagsResponse)
async def list_document_tags(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
) -> DocumentTagsResponse:
    """List all tags on a document."""
    tags = await DatasetService.list_document_tags(db, document_id, matter_id)
    return DocumentTagsResponse(document_id=document_id, tags=tags)


@router.get("/tags", response_model=list[TagResponse])
async def list_all_tags(
    db: AsyncSession = Depends(get_db),
    _user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
) -> list[TagResponse]:
    """List all tags in the current matter with document counts."""
    return await DatasetService.list_all_tags(db, matter_id)


@router.get("/tags/{tag_name}/documents")
async def list_documents_by_tag(
    tag_name: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
):
    """List documents with a specific tag."""
    items, total = await DatasetService.list_documents_by_tag(
        db,
        tag_name,
        matter_id,
        offset,
        limit,
    )
    return {"items": items, "total": total, "offset": offset, "limit": limit}


# ------------------------------------------------------------------
# Dataset ingestion
# ------------------------------------------------------------------


@router.post(
    "/datasets/{dataset_id}/ingest",
    response_model=DatasetIngestResponse,
)
async def ingest_dataset(
    dataset_id: UUID,
    request: DatasetIngestRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(require_role("admin", "attorney")),
    matter_id: UUID = Depends(get_matter_id),
) -> DatasetIngestResponse:
    """Kick off a bulk import into a dataset."""
    from app.ingestion.bulk_import import (
        _get_sync_engine,
        build_adapter,
        create_bulk_import_job,
    )
    from app.ingestion.tasks import run_bulk_import

    # Validate dataset exists
    ds = await DatasetService.get_dataset(db, dataset_id, matter_id)
    if ds is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    # Build source_config from request
    source_config = _build_source_config(request)

    # Validate adapter + path
    try:
        adapter = build_adapter(request.adapter_type, source_config)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Count documents (quick scan)
    doc_count = sum(1 for _ in adapter.iter_documents(limit=request.limit))
    if doc_count == 0:
        raise HTTPException(
            status_code=400,
            detail="No documents found at source path",
        )

    # Create bulk import job row
    engine = _get_sync_engine()
    try:
        bulk_job_id = create_bulk_import_job(
            engine,
            str(matter_id),
            request.adapter_type,
            request.source_path,
            doc_count,
        )
    finally:
        engine.dispose()

    # Dispatch Celery task
    run_bulk_import.delay(
        bulk_job_id=bulk_job_id,
        adapter_type=request.adapter_type,
        source_config=source_config,
        matter_id=str(matter_id),
        dataset_id=str(dataset_id),
        options={
            "resume": request.resume,
            "limit": request.limit,
            "disable_hnsw": request.disable_hnsw,
        },
    )

    logger.info(
        "dataset.ingest.started",
        dataset_id=str(dataset_id),
        bulk_job_id=bulk_job_id,
        adapter_type=request.adapter_type,
        total_documents=doc_count,
    )

    return DatasetIngestResponse(
        bulk_job_id=bulk_job_id,
        total_documents=doc_count,
        status="processing",
    )


@router.post(
    "/datasets/{dataset_id}/ingest/dry-run",
    response_model=DryRunEstimate,
)
async def ingest_dry_run(
    dataset_id: UUID,
    request: DatasetIngestRequest,
    db: AsyncSession = Depends(get_db),
    _user: UserRecord = Depends(require_role("admin", "attorney")),
    matter_id: UUID = Depends(get_matter_id),
) -> DryRunEstimate:
    """Count documents and estimate costs without dispatching any tasks."""
    from app.ingestion.bulk_import import (
        AVG_CHUNKS_PER_DOC,
        AVG_TOKENS_PER_CHUNK,
        EMBEDDING_COST_PER_M_TOKENS,
        build_adapter,
    )

    # Validate dataset exists
    ds = await DatasetService.get_dataset(db, dataset_id, matter_id)
    if ds is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    source_config = _build_source_config(request)

    try:
        adapter = build_adapter(request.adapter_type, source_config)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    doc_count = 0
    total_chars = 0
    for doc in adapter.iter_documents(limit=request.limit):
        doc_count += 1
        total_chars += len(doc.text)

    est_chunks = int(doc_count * AVG_CHUNKS_PER_DOC)
    est_tokens = est_chunks * AVG_TOKENS_PER_CHUNK
    est_cost = (est_tokens / 1_000_000) * EMBEDDING_COST_PER_M_TOKENS

    return DryRunEstimate(
        total_documents=doc_count,
        total_characters=total_chars,
        estimated_chunks=est_chunks,
        estimated_tokens=est_tokens,
        estimated_cost_usd=round(est_cost, 4),
    )


@router.get(
    "/datasets/{dataset_id}/ingest/status",
    response_model=list[BulkImportStatusResponse],
)
async def list_ingest_jobs(
    dataset_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
) -> list[BulkImportStatusResponse]:
    """List bulk import jobs for a dataset."""
    from sqlalchemy import text

    # Validate dataset exists
    ds = await DatasetService.get_dataset(db, dataset_id, matter_id)
    if ds is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    result = await db.execute(
        text(
            """
            SELECT b.id, b.status, b.adapter_type, b.source_path,
                   b.total_documents, b.processed_documents,
                   b.failed_documents, b.skipped_documents,
                   b.created_at, b.completed_at, b.error
            FROM bulk_import_jobs b
            WHERE b.matter_id = :matter_id
            ORDER BY b.created_at DESC
            LIMIT 50
            """
        ),
        {"matter_id": str(matter_id)},
    )
    rows = result.fetchall()
    return [
        BulkImportStatusResponse(
            id=str(row.id),
            status=row.status,
            adapter_type=row.adapter_type,
            source_path=row.source_path,
            total_documents=row.total_documents,
            processed_documents=row.processed_documents,
            failed_documents=row.failed_documents,
            skipped_documents=row.skipped_documents,
            created_at=str(row.created_at),
            completed_at=(str(row.completed_at) if row.completed_at else None),
            error=row.error,
        )
        for row in rows
    ]


@router.get(
    "/datasets/{dataset_id}/ingest/{bulk_job_id}",
    response_model=BulkImportStatusResponse,
)
async def get_ingest_job(
    dataset_id: UUID,
    bulk_job_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
) -> BulkImportStatusResponse:
    """Get a single bulk import job's progress."""
    from sqlalchemy import text

    result = await db.execute(
        text(
            """
            SELECT id, status, adapter_type, source_path,
                   total_documents, processed_documents,
                   failed_documents, skipped_documents,
                   created_at, completed_at, error
            FROM bulk_import_jobs
            WHERE id = :id AND matter_id = :matter_id
            """
        ),
        {"id": str(bulk_job_id), "matter_id": str(matter_id)},
    )
    row = result.first()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail="Bulk import job not found",
        )

    return BulkImportStatusResponse(
        id=str(row.id),
        status=row.status,
        adapter_type=row.adapter_type,
        source_path=row.source_path,
        total_documents=row.total_documents,
        processed_documents=row.processed_documents,
        failed_documents=row.failed_documents,
        skipped_documents=row.skipped_documents,
        created_at=str(row.created_at),
        completed_at=(str(row.completed_at) if row.completed_at else None),
        error=row.error,
    )


def _build_source_config(request: DatasetIngestRequest) -> dict:
    """Build the adapter source_config dict from the request."""
    if request.adapter_type == "directory":
        return {"data_dir": request.source_path}
    elif request.adapter_type == "huggingface_csv":
        return {"file_path": request.source_path}
    elif request.adapter_type in ("edrm_xml", "concordance_dat"):
        config: dict = {"file_path": request.source_path}
        if request.content_dir:
            config["content_dir"] = request.content_dir
        return config
    else:
        return {"file_path": request.source_path}


# ------------------------------------------------------------------
# Access control
# ------------------------------------------------------------------


@router.post("/datasets/{dataset_id}/access", response_model=DatasetAccessResponse, status_code=201)
async def grant_access(
    dataset_id: UUID,
    request: DatasetAccessRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(require_role("admin", "attorney")),
    matter_id: UUID = Depends(get_matter_id),
) -> DatasetAccessResponse:
    """Grant a user access to a dataset."""
    try:
        result = await DatasetService.grant_access(
            db,
            dataset_id,
            request.user_id,
            request.access_role,
            current_user.id,
            matter_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    await db.commit()
    return result


@router.delete("/datasets/{dataset_id}/access/{user_id}", status_code=204)
async def revoke_access(
    dataset_id: UUID,
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: UserRecord = Depends(require_role("admin", "attorney")),
    matter_id: UUID = Depends(get_matter_id),
):
    """Revoke a user's access to a dataset."""
    try:
        revoked = await DatasetService.revoke_access(db, dataset_id, user_id, matter_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    if not revoked:
        raise HTTPException(status_code=404, detail="Access entry not found")
    await db.commit()


@router.get("/datasets/{dataset_id}/access", response_model=list[DatasetAccessResponse])
async def list_access(
    dataset_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: UserRecord = Depends(require_role("admin", "attorney")),
    matter_id: UUID = Depends(get_matter_id),
) -> list[DatasetAccessResponse]:
    """List all access entries for a dataset."""
    try:
        return await DatasetService.list_access(db, dataset_id, matter_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
