"""Pydantic schemas for the annotations domain."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel

from app.common.models import PaginatedResponse


class AnnotationType(StrEnum):
    """Types of document annotations."""

    NOTE = "note"
    HIGHLIGHT = "highlight"
    TAG = "tag"


class AnnotationCreate(BaseModel):
    """Request body for creating an annotation."""

    document_id: UUID
    page_number: int | None = None
    annotation_type: AnnotationType = AnnotationType.NOTE
    content: str
    anchor: dict = {}
    color: str | None = None


class AnnotationUpdate(BaseModel):
    """Request body for updating an annotation (all fields optional)."""

    content: str | None = None
    anchor: dict | None = None
    color: str | None = None


class AnnotationResponse(BaseModel):
    """Response model for a single annotation."""

    id: UUID
    document_id: UUID
    matter_id: UUID
    user_id: UUID
    page_number: int | None = None
    annotation_type: str
    content: str
    anchor: dict
    color: str | None = None
    created_at: datetime
    updated_at: datetime


class AnnotationListResponse(PaginatedResponse[AnnotationResponse]):
    """Paginated list of annotations."""
