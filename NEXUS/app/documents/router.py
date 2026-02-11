"""Document management API endpoints.

GET /documents                    -- list ingested documents (filterable)
GET /documents/{doc_id}           -- document metadata + chunks
GET /documents/{doc_id}/preview   -- page thumbnail
GET /documents/{doc_id}/download  -- original file from MinIO
"""

from fastapi import APIRouter

router = APIRouter(tags=["documents"])


@router.get("/documents")
async def list_documents():
    """List all ingested documents with optional filters."""
    return {"detail": "not implemented"}


@router.get("/documents/{doc_id}")
async def get_document(doc_id: str):
    """Return metadata and chunk summary for a single document."""
    return {"detail": "not implemented", "doc_id": doc_id}


@router.get("/documents/{doc_id}/preview")
async def document_preview(doc_id: str):
    """Return a page thumbnail for the document."""
    return {"detail": "not implemented", "doc_id": doc_id}


@router.get("/documents/{doc_id}/download")
async def document_download(doc_id: str):
    """Serve the original uploaded file from MinIO."""
    return {"detail": "not implemented", "doc_id": doc_id}
