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
    DatasetAccessRequest,
    DatasetAccessResponse,
    DatasetCreateRequest,
    DatasetListResponse,
    DatasetResponse,
    DatasetTreeResponse,
    DatasetUpdateRequest,
    DocumentTagsResponse,
    MoveDocumentsRequest,
    TagRequest,
    TagResponse,
)
from app.datasets.service import DatasetService
from app.dependencies import get_db

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


@router.get("/datasets/{dataset_id}/documents")
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
    return {"items": items, "total": total, "offset": offset, "limit": limit}


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
