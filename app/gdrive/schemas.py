"""Google Drive integration Pydantic schemas."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ConnectionType(StrEnum):
    OAUTH = "oauth"
    SERVICE_ACCOUNT = "service_account"


class SyncStatus(StrEnum):
    SYNCED = "synced"
    MODIFIED = "modified"
    DELETED = "deleted"
    PENDING = "pending"
    ERROR = "error"


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class GDriveAuthURLRequest(BaseModel):
    """Query params for generating the OAuth URL."""

    pass


class GDriveIngestRequest(BaseModel):
    """Select files/folders from a connected Drive for ingestion."""

    connection_id: UUID
    file_ids: list[str] = Field(default_factory=list, description="Individual Drive file IDs")
    folder_ids: list[str] = Field(default_factory=list, description="Drive folder IDs to recursively import")
    dataset_id: UUID | None = Field(default=None, description="Target dataset for imported documents")


class GDriveSyncRequest(BaseModel):
    """Re-sync a previously imported connection."""

    connection_id: UUID


class GDriveBrowseRequest(BaseModel):
    """Query params for browsing Drive contents."""

    connection_id: UUID
    folder_id: str = Field(default="root", description="Drive folder ID to list (default: root)")
    page_token: str | None = None
    page_size: int = Field(default=50, ge=1, le=1000)


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class GDriveAuthURLResponse(BaseModel):
    auth_url: str


class GDriveConnectionResponse(BaseModel):
    id: UUID
    connection_type: ConnectionType
    email: str
    is_active: bool
    scopes: str
    created_at: datetime
    updated_at: datetime


class GDriveConnectionListResponse(BaseModel):
    connections: list[GDriveConnectionResponse]


class GDriveFileItem(BaseModel):
    id: str
    name: str
    mime_type: str
    size: int | None = None
    modified_time: str | None = None
    is_folder: bool = False


class GDriveBrowseResponse(BaseModel):
    files: list[GDriveFileItem]
    next_page_token: str | None = None


class GDriveIngestResponse(BaseModel):
    job_id: UUID
    file_count: int
    message: str


class GDriveSyncStateItem(BaseModel):
    id: UUID
    drive_file_id: str
    drive_file_name: str
    sync_status: SyncStatus
    last_synced_at: datetime | None = None
    document_id: UUID | None = None


class GDriveSyncStatusResponse(BaseModel):
    connection_id: UUID
    items: list[GDriveSyncStateItem]
    total: int
