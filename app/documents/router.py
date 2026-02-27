"""Document management API endpoints.

GET   /documents                    -- list ingested documents (filterable)
GET   /documents/{doc_id}           -- document metadata
GET   /documents/{doc_id}/preview   -- page thumbnail (presigned URL)
GET   /documents/{doc_id}/download  -- original file from MinIO (presigned URL)
PATCH /documents/{doc_id}/privilege -- update privilege status (admin/attorney/paralegal)
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.middleware import get_current_user, get_matter_id, require_role
from app.common.storage import StorageClient
from app.common.vector_store import VectorStoreClient
from app.dependencies import get_db, get_minio, get_qdrant, get_graph_service
from app.documents.schemas import (
    DocumentDetail,
    DocumentListResponse,
    DocumentPreview,
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
    )


# -----------------------------------------------------------------------
# GET /documents — list ingested documents (filterable)
# -----------------------------------------------------------------------

@router.get("/documents", response_model=DocumentListResponse)
async def list_documents(
    document_type: str | None = Query(None, description="Filter by document type"),
    q: str | None = Query(None, description="Search by filename (case-insensitive)"),
    offset: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=200, description="Max records to return"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
):
    """List all ingested documents with optional filters."""
    items, total = await DocumentService.list_documents(
        db=db,
        document_type=document_type,
        filename_search=q,
        offset=offset,
        limit=limit,
        matter_id=matter_id,
        user_role=current_user["role"],
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
    current_user: dict = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
):
    """Return metadata for a single document."""
    row = await DocumentService.get_document(
        db=db, doc_id=doc_id, matter_id=matter_id, user_role=current_user["role"],
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")
    return _row_to_detail(row)


# -----------------------------------------------------------------------
# GET /documents/{doc_id}/preview — page thumbnail (presigned URL)
# -----------------------------------------------------------------------

@router.get("/documents/{doc_id}/preview", response_model=DocumentPreview)
async def document_preview(
    doc_id: UUID,
    page: int = Query(1, ge=1, description="Page number to preview"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
    storage: StorageClient = Depends(get_minio),
):
    """Return a presigned URL to a page thumbnail for the document."""
    row = await DocumentService.get_document(
        db=db, doc_id=doc_id, matter_id=matter_id, user_role=current_user["role"],
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")

    preview_key = f"pages/{doc_id}/page_{page:03d}.png"
    url = await storage.get_presigned_url(preview_key)

    return DocumentPreview(doc_id=doc_id, page=page, image_url=url)


# -----------------------------------------------------------------------
# GET /documents/{doc_id}/download — original file from MinIO
# -----------------------------------------------------------------------

@router.get("/documents/{doc_id}/download")
async def document_download(
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
    storage: StorageClient = Depends(get_minio),
):
    """Return a presigned URL to download the original uploaded file."""
    row = await DocumentService.get_document(
        db=db, doc_id=doc_id, matter_id=matter_id, user_role=current_user["role"],
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")

    url = await storage.get_presigned_url(row["minio_path"])
    return {"doc_id": str(doc_id), "filename": row["filename"], "download_url": url}


# -----------------------------------------------------------------------
# PATCH /documents/{doc_id}/privilege — update privilege status
# -----------------------------------------------------------------------

@router.patch("/documents/{doc_id}/privilege", response_model=PrivilegeUpdateResponse)
async def update_document_privilege(
    doc_id: UUID,
    body: PrivilegeUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_role("admin", "attorney", "paralegal")),
    matter_id: UUID = Depends(get_matter_id),
    qdrant: VectorStoreClient = Depends(get_qdrant),
    gs: GraphService = Depends(get_graph_service),
):
    """Tag a document's privilege status. Reviewer role is excluded."""
    # Verify doc exists (no role filtering — admin/attorney/paralegal can all see)
    row = await DocumentService.get_document(db=db, doc_id=doc_id, matter_id=matter_id, user_role="admin")
    if row is None:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")

    # Update PostgreSQL
    updated = await DocumentService.update_privilege(
        db=db,
        doc_id=doc_id,
        privilege_status=body.privilege_status.value,
        reviewed_by=current_user["id"],
    )
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")

    # Update Qdrant payload (uses job_id as doc identifier)
    job_id = str(row["job_id"])
    await qdrant.update_privilege_status(doc_id=job_id, privilege_status=body.privilege_status.value)

    # Update Neo4j Document node
    await gs.update_document_privilege(doc_id=job_id, privilege_status=body.privilege_status.value)

    await db.commit()

    return PrivilegeUpdateResponse(**updated)
