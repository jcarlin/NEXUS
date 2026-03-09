"""Document management API endpoints.

GET   /documents                    -- list ingested documents (filterable)
GET   /documents/{doc_id}           -- document metadata
GET   /documents/{doc_id}/preview   -- page thumbnail PNG (streamed bytes)
GET   /documents/{doc_id}/download  -- original file from MinIO (streamed bytes)
PATCH /documents/{doc_id}/privilege -- update privilege status (admin/attorney/paralegal)
"""

from __future__ import annotations

import mimetypes
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.middleware import get_current_user, get_matter_id, require_role
from app.auth.schemas import UserRecord
from app.common.storage import StorageClient
from app.common.vector_store import VectorStoreClient
from app.dependencies import get_db, get_graph_service, get_minio, get_qdrant
from app.documents.schemas import (
    DocumentDetail,
    DocumentHealthItem,
    DocumentHealthResponse,
    DocumentListResponse,
    DocumentResponse,
    PrivilegeUpdateRequest,
    PrivilegeUpdateResponse,
)
from app.documents.service import DocumentService
from app.entities.graph_service import GraphService

router = APIRouter(tags=["documents"])


# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------


def _row_to_response(row: dict) -> DocumentResponse:
    """Convert a raw DB row dict into a ``DocumentResponse``."""
    return DocumentResponse(
        id=row["id"],
        filename=row["filename"],
        type=row.get("document_type"),
        page_count=row.get("page_count", 0),
        chunk_count=row.get("chunk_count", 0),
        entity_count=row.get("entity_count", 0),
        created_at=row["created_at"],
        minio_path=row["minio_path"],
        privilege_status=row.get("privilege_status"),
        thread_id=row.get("thread_id"),
        is_inclusive=row.get("is_inclusive"),
        duplicate_cluster_id=row.get("duplicate_cluster_id"),
        version_group_id=row.get("version_group_id"),
        hot_doc_score=row.get("hot_doc_score"),
    )


def _row_to_detail(row: dict) -> DocumentDetail:
    """Convert a raw DB row dict into a ``DocumentDetail``."""
    return DocumentDetail(
        id=row["id"],
        filename=row["filename"],
        type=row.get("document_type"),
        page_count=row.get("page_count", 0),
        chunk_count=row.get("chunk_count", 0),
        entity_count=row.get("entity_count", 0),
        created_at=row["created_at"],
        minio_path=row["minio_path"],
        metadata_=row.get("metadata_") or {},
        file_size_bytes=row.get("file_size_bytes"),
        content_hash=row.get("content_hash"),
        job_id=row.get("job_id"),
        updated_at=row.get("updated_at"),
        privilege_status=row.get("privilege_status"),
        privilege_reviewed_by=row.get("privilege_reviewed_by"),
        privilege_reviewed_at=row.get("privilege_reviewed_at"),
        thread_id=row.get("thread_id"),
        is_inclusive=row.get("is_inclusive"),
        duplicate_cluster_id=row.get("duplicate_cluster_id"),
        version_group_id=row.get("version_group_id"),
        hot_doc_score=row.get("hot_doc_score"),
        message_id=row.get("message_id"),
        in_reply_to=row.get("in_reply_to"),
        thread_position=row.get("thread_position"),
        duplicate_score=row.get("duplicate_score"),
        version_number=row.get("version_number"),
        is_final_version=row.get("is_final_version"),
        sentiment_positive=row.get("sentiment_positive"),
        sentiment_negative=row.get("sentiment_negative"),
        sentiment_pressure=row.get("sentiment_pressure"),
        sentiment_opportunity=row.get("sentiment_opportunity"),
        sentiment_rationalization=row.get("sentiment_rationalization"),
        sentiment_intent=row.get("sentiment_intent"),
        sentiment_concealment=row.get("sentiment_concealment"),
        context_gap_score=row.get("context_gap_score"),
        context_gaps=row.get("context_gaps") or [],
        anomaly_score=row.get("anomaly_score"),
        bates_begin=row.get("bates_begin"),
        bates_end=row.get("bates_end"),
    )


# -----------------------------------------------------------------------
# GET /documents/health — check vector index health
# -----------------------------------------------------------------------


@router.get("/documents/health", response_model=DocumentHealthResponse)
async def check_document_health(
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(require_role("admin", "attorney")),
    matter_id: UUID = Depends(get_matter_id),
    qdrant: VectorStoreClient = Depends(get_qdrant),
):
    """Compare expected chunk counts (PG) vs indexed points (Qdrant)."""
    items = await DocumentService.check_ingestion_health(
        db=db,
        qdrant=qdrant,
        matter_id=matter_id,
    )
    health_items = [DocumentHealthItem(**item) for item in items]
    healthy = sum(1 for i in health_items if i.status == "healthy")
    missing = sum(1 for i in health_items if i.status == "missing")
    partial = sum(1 for i in health_items if i.status == "partial")
    return DocumentHealthResponse(
        total=len(health_items),
        healthy=healthy,
        missing=missing,
        partial=partial,
        documents=health_items,
    )


# -----------------------------------------------------------------------
# GET /documents — list ingested documents (filterable)
# -----------------------------------------------------------------------


@router.get("/documents", response_model=DocumentListResponse)
async def list_documents(
    document_type: str | None = Query(None, description="Filter by document type"),
    file_extension: str | None = Query(None, description="Filter by file extension (e.g. pdf, docx)"),
    q: str | None = Query(None, description="Search by filename (case-insensitive)"),
    hot_doc_score_min: float | None = Query(None, ge=0.0, le=1.0, description="Minimum hot doc score"),
    anomaly_score_min: float | None = Query(None, ge=0.0, le=1.0, description="Minimum anomaly score"),
    dataset_id: UUID | None = Query(default=None, description="Filter by dataset"),
    tag_name: str | None = Query(default=None, description="Filter by tag"),
    offset: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=200, description="Max records to return"),
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
):
    """List all ingested documents with optional filters."""
    items, total = await DocumentService.list_documents(
        db=db,
        document_type=document_type,
        file_extension=file_extension,
        filename_search=q,
        hot_doc_score_min=hot_doc_score_min,
        anomaly_score_min=anomaly_score_min,
        offset=offset,
        limit=limit,
        matter_id=matter_id,
        user_role=current_user.role,
        dataset_id=dataset_id,
        tag_name=tag_name,
    )
    return DocumentListResponse(
        items=[_row_to_response(row) for row in items],
        total=total,
        offset=offset,
        limit=limit,
    )


# -----------------------------------------------------------------------
# GET /documents/{doc_id} — document metadata
# -----------------------------------------------------------------------


@router.get("/documents/{doc_id}", response_model=DocumentDetail)
async def get_document(
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
):
    """Return metadata for a single document."""
    row = await DocumentService.get_document(
        db=db,
        doc_id=doc_id,
        matter_id=matter_id,
        user_role=current_user.role,
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")
    return _row_to_detail(row)


# -----------------------------------------------------------------------
# GET /documents/{doc_id}/preview — page thumbnail (presigned URL)
# -----------------------------------------------------------------------


@router.get("/documents/{doc_id}/preview")
async def document_preview(
    doc_id: UUID,
    page: int = Query(1, ge=1, description="Page number to preview"),
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
    storage: StorageClient = Depends(get_minio),
):
    """Return a page thumbnail PNG for the document."""
    row = await DocumentService.get_document(
        db=db,
        doc_id=doc_id,
        matter_id=matter_id,
        user_role=current_user.role,
    )
    if row is None:
        # Qdrant payloads store job_id as doc_id — try fallback
        row = await DocumentService.get_document_by_job(
            db=db,
            job_id=doc_id,
            matter_id=matter_id,
            user_role=current_user.role,
        )
    if row is None:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")

    # Page images are always stored under job_id in MinIO
    page_key_id = str(row["job_id"]) if row.get("job_id") else str(doc_id)
    preview_key = f"pages/{page_key_id}/page_{page:03d}.png"
    try:
        data = await storage.download_bytes(preview_key)
    except Exception:
        raise HTTPException(status_code=404, detail="Preview not available")
    return Response(content=data, media_type="image/png")


# -----------------------------------------------------------------------
# GET /documents/{doc_id}/download — original file from MinIO
# -----------------------------------------------------------------------


@router.get("/documents/{doc_id}/download")
async def document_download(
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
    storage: StorageClient = Depends(get_minio),
):
    """Download the original uploaded file."""
    row = await DocumentService.get_document(
        db=db,
        doc_id=doc_id,
        matter_id=matter_id,
        user_role=current_user.role,
    )
    if row is None:
        # Qdrant payloads store job_id as doc_id — try fallback
        row = await DocumentService.get_document_by_job(
            db=db,
            job_id=doc_id,
            matter_id=matter_id,
            user_role=current_user.role,
        )
    if row is None:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")

    data = await storage.download_bytes(row["minio_path"])
    content_type, _ = mimetypes.guess_type(row["filename"])
    return Response(
        content=data,
        media_type=content_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{row["filename"]}"'},
    )


# -----------------------------------------------------------------------
# PATCH /documents/{doc_id}/privilege — update privilege status
# -----------------------------------------------------------------------


@router.patch("/documents/{doc_id}/privilege", response_model=PrivilegeUpdateResponse)
async def update_document_privilege(
    doc_id: UUID,
    body: PrivilegeUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(require_role("admin", "attorney", "paralegal")),
    matter_id: UUID = Depends(get_matter_id),
    qdrant: VectorStoreClient = Depends(get_qdrant),
    gs: GraphService = Depends(get_graph_service),
):
    """Tag a document's privilege status. Reviewer role is excluded."""
    row = await DocumentService.get_document(db=db, doc_id=doc_id, matter_id=matter_id, user_role="admin")
    if row is None:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")

    updated = await DocumentService.update_privilege_across_stores(
        db=db,
        doc_id=doc_id,
        privilege_status=body.privilege_status.value,
        reviewed_by=current_user.id,
        qdrant=qdrant,
        gs=gs,
        job_id=str(row["job_id"]),
    )
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")

    await db.commit()

    return PrivilegeUpdateResponse(**updated)
