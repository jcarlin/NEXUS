"""Pydantic schemas for external task tracking."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.common.models import PaginatedResponse


class ExternalTaskRegisterRequest(BaseModel):
    """Register a new external script task."""

    name: str = Field(..., min_length=1, max_length=200)
    script_name: str = Field(..., min_length=1, max_length=200)
    total: int = Field(default=0, ge=0)
    metadata_: dict = Field(default_factory=dict)
    matter_id: UUID | None = None


class ExternalTaskUpdateRequest(BaseModel):
    """Update progress on an external task."""

    processed: int | None = Field(default=None, ge=0)
    failed: int | None = Field(default=None, ge=0)
    error: str | None = None
    status: str | None = Field(default=None, pattern="^(running|complete|failed)$")
    total: int | None = Field(default=None, ge=0)


class ExternalTaskResponse(BaseModel):
    """Full view of an external task."""

    id: UUID
    name: str
    script_name: str
    status: str
    total: int
    processed: int
    failed: int
    error: str | None
    metadata_: dict = Field(default_factory=dict)
    matter_id: UUID | None
    started_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class ExternalTaskListResponse(PaginatedResponse[ExternalTaskResponse]):
    """Paginated list of external tasks."""
