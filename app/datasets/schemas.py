"""Dataset and collection management Pydantic schemas."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field

from app.common.models import PaginatedResponse


class DatasetAccessRole(StrEnum):
    VIEWER = "viewer"
    EDITOR = "editor"
    ADMIN = "admin"


# ---------------------------------------------------------------------------
# Dataset CRUD
# ---------------------------------------------------------------------------


class DatasetCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str = Field(default="")
    parent_id: UUID | None = Field(default=None, description="Parent dataset ID for nested folders")


class DatasetUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    parent_id: UUID | None = Field(default=None, description="Move dataset under a new parent (null = root)")


class DatasetResponse(BaseModel):
    id: UUID
    matter_id: UUID
    name: str
    description: str
    parent_id: UUID | None
    document_count: int = 0
    children_count: int = 0
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime


class DatasetTreeNode(BaseModel):
    id: UUID
    name: str
    description: str
    document_count: int = 0
    children: list[DatasetTreeNode] = Field(default_factory=list)


class DatasetTreeResponse(BaseModel):
    roots: list[DatasetTreeNode]
    total_datasets: int


class DatasetListResponse(PaginatedResponse[DatasetResponse]):
    """Paginated list of datasets."""


# ---------------------------------------------------------------------------
# Document assignment
# ---------------------------------------------------------------------------


class AssignDocumentsRequest(BaseModel):
    document_ids: list[UUID] = Field(..., min_length=1, max_length=500)


class MoveDocumentsRequest(BaseModel):
    document_ids: list[UUID] = Field(..., min_length=1, max_length=500)
    target_dataset_id: UUID


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------


class TagRequest(BaseModel):
    tag_name: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9 _-]*$")


class TagResponse(BaseModel):
    tag_name: str
    document_count: int = 0


class DocumentTagsResponse(BaseModel):
    document_id: UUID
    tags: list[str]


# ---------------------------------------------------------------------------
# Access control
# ---------------------------------------------------------------------------


class DatasetAccessRequest(BaseModel):
    user_id: UUID
    access_role: DatasetAccessRole = DatasetAccessRole.VIEWER


class DatasetAccessResponse(BaseModel):
    id: UUID
    dataset_id: UUID
    user_id: UUID
    access_role: DatasetAccessRole
    granted_by: UUID | None = None
    granted_at: datetime


# ---------------------------------------------------------------------------
# Dataset ingestion
# ---------------------------------------------------------------------------


class DatasetIngestRequest(BaseModel):
    adapter_type: str = Field(
        ...,
        description="Adapter type: directory, huggingface_csv, edrm_xml, concordance_dat",
    )
    source_path: str = Field(
        ...,
        min_length=1,
        description="Primary path (directory or file)",
    )
    content_dir: str | None = Field(
        default=None,
        description="Content directory for EDRM/Concordance referenced files",
    )
    resume: bool = Field(
        default=False,
        description="Skip documents whose content hash already exists",
    )
    limit: int | None = Field(
        default=None,
        ge=1,
        description="Import at most N documents",
    )
    disable_hnsw: bool = Field(
        default=False,
        description="Disable HNSW indexing during import for faster inserts",
    )


class DatasetIngestResponse(BaseModel):
    bulk_job_id: str
    total_documents: int
    status: str


class DryRunEstimate(BaseModel):
    total_documents: int
    total_characters: int
    estimated_chunks: int
    estimated_tokens: int
    estimated_cost_usd: float


class BulkImportStatusResponse(BaseModel):
    id: str
    status: str
    adapter_type: str
    source_path: str
    total_documents: int
    processed_documents: int
    failed_documents: int
    skipped_documents: int
    created_at: str
    completed_at: str | None = None
    error: str | None = None
