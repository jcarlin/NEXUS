"""Annotation management API endpoints.

POST   /annotations                       -- create an annotation
GET    /annotations                        -- list annotations (filterable)
GET    /annotations/{annotation_id}        -- annotation detail
PATCH  /annotations/{annotation_id}        -- update an annotation
DELETE /annotations/{annotation_id}        -- delete an annotation
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.annotations.schemas import (
    AnnotationCreate,
    AnnotationListResponse,
    AnnotationResponse,
    AnnotationUpdate,
)
from app.annotations.service import AnnotationService
from app.auth.middleware import get_current_user, get_matter_id
from app.auth.schemas import UserRecord
from app.dependencies import get_db

router = APIRouter(tags=["annotations"])


# -----------------------------------------------------------------------
# POST /annotations — create annotation
# -----------------------------------------------------------------------


@router.post(
    "/annotations",
    response_model=AnnotationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_annotation(
    body: AnnotationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
):
    """Create a new annotation on a document."""
    try:
        row = await AnnotationService.create_annotation(
            db=db,
            matter_id=matter_id,
            user_id=current_user.id,
            data=body,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return AnnotationResponse(**row)


# -----------------------------------------------------------------------
# GET /annotations — list annotations (filterable)
# -----------------------------------------------------------------------


@router.get("/annotations", response_model=AnnotationListResponse)
async def list_annotations(
    document_id: UUID | None = Query(None, description="Filter by document"),
    offset: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=200, description="Max records to return"),
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
):
    """List annotations with optional filters."""
    items, total = await AnnotationService.list_annotations(
        db=db,
        matter_id=matter_id,
        document_id=document_id,
        offset=offset,
        limit=limit,
    )
    return AnnotationListResponse(
        items=[AnnotationResponse(**row) for row in items],
        total=total,
        offset=offset,
        limit=limit,
    )


# -----------------------------------------------------------------------
# GET /annotations/{annotation_id} — annotation detail
# -----------------------------------------------------------------------


@router.get("/annotations/{annotation_id}", response_model=AnnotationResponse)
async def get_annotation(
    annotation_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
):
    """Return a single annotation by ID."""
    row = await AnnotationService.get_annotation(
        db=db,
        annotation_id=annotation_id,
        matter_id=matter_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"Annotation {annotation_id} not found")
    return AnnotationResponse(**row)


# -----------------------------------------------------------------------
# PATCH /annotations/{annotation_id} — update annotation
# -----------------------------------------------------------------------


@router.patch("/annotations/{annotation_id}", response_model=AnnotationResponse)
async def update_annotation(
    annotation_id: UUID,
    body: AnnotationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
):
    """Update an annotation.  Only the annotation owner can edit."""
    row = await AnnotationService.update_annotation(
        db=db,
        annotation_id=annotation_id,
        matter_id=matter_id,
        user_id=current_user.id,
        data=body,
    )
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"Annotation {annotation_id} not found or not owned by current user",
        )
    return AnnotationResponse(**row)


# -----------------------------------------------------------------------
# DELETE /annotations/{annotation_id} — delete annotation
# -----------------------------------------------------------------------


@router.delete(
    "/annotations/{annotation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_annotation(
    annotation_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
):
    """Delete an annotation.  Only the annotation owner can delete."""
    deleted = await AnnotationService.delete_annotation(
        db=db,
        annotation_id=annotation_id,
        matter_id=matter_id,
        user_id=current_user.id,
    )
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Annotation {annotation_id} not found or not owned by current user",
        )
