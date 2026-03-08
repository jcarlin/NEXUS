"""Google Drive integration API endpoints.

All endpoints are matter-scoped and require authentication.
The router is only mounted when ``ENABLE_GOOGLE_DRIVE=true``.
"""

from __future__ import annotations

from uuid import UUID

import jwt as pyjwt
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.middleware import get_current_user, get_matter_id
from app.auth.schemas import UserRecord
from app.dependencies import get_db, get_settings
from app.gdrive.schemas import (
    GDriveAuthURLResponse,
    GDriveBrowseResponse,
    GDriveConnectionListResponse,
    GDriveConnectionResponse,
    GDriveFileItem,
    GDriveIngestRequest,
    GDriveIngestResponse,
    GDriveSyncRequest,
    GDriveSyncStateItem,
    GDriveSyncStatusResponse,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/gdrive", tags=["gdrive"])


def _get_gdrive_service():
    """Lazy import to avoid loading google libs when feature is disabled."""
    from app.dependencies import get_gdrive_service

    return get_gdrive_service()


# ---------------------------------------------------------------------------
# OAuth flow
# ---------------------------------------------------------------------------


@router.get("/auth/url", response_model=GDriveAuthURLResponse)
async def get_auth_url(
    current_user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
) -> GDriveAuthURLResponse:
    """Generate a Google OAuth2 authorization URL."""
    settings = get_settings()
    service = _get_gdrive_service()

    # Sign a JWT state param with user_id + matter_id for CSRF protection
    state_payload = {
        "sub": str(current_user.id),
        "matter_id": str(matter_id),
    }
    state_token = pyjwt.encode(state_payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    auth_url = service.build_auth_url(state=state_token)
    return GDriveAuthURLResponse(auth_url=auth_url)


@router.get("/auth/callback")
async def auth_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> GDriveConnectionResponse:
    """Exchange OAuth code for tokens and store the connection."""
    settings = get_settings()
    service = _get_gdrive_service()

    # Validate state JWT
    try:
        payload = pyjwt.decode(state, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except pyjwt.PyJWTError:
        raise HTTPException(status_code=400, detail="Invalid state parameter")

    user_id = UUID(payload["sub"])
    matter_id = UUID(payload["matter_id"])

    # Exchange code for tokens
    tokens = service.exchange_code(code)

    # Get the user's email from the Drive API
    import json

    email = service.get_user_email(json.dumps(tokens))

    # Store encrypted
    connection_id = await service.store_connection(
        db,
        user_id,
        matter_id,
        tokens,
        email,
    )

    # Fetch the stored connection for the response
    connections = await service.get_connections(db, matter_id, user_id)
    conn = next(c for c in connections if c["id"] == connection_id)
    return GDriveConnectionResponse(**conn)


# ---------------------------------------------------------------------------
# Connection management
# ---------------------------------------------------------------------------


@router.get("/connections", response_model=GDriveConnectionListResponse)
async def list_connections(
    current_user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
    db: AsyncSession = Depends(get_db),
) -> GDriveConnectionListResponse:
    """List active Google Drive connections for the current matter."""
    service = _get_gdrive_service()
    connections = await service.get_connections(db, matter_id, current_user.id)
    return GDriveConnectionListResponse(
        connections=[GDriveConnectionResponse(**c) for c in connections],
    )


@router.delete("/connections/{connection_id}", status_code=204, response_model=None)
async def delete_connection(
    connection_id: UUID,
    current_user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Revoke and delete a Google Drive connection."""
    service = _get_gdrive_service()
    deleted = await service.delete_connection(db, connection_id, matter_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Connection not found")
    logger.info("gdrive.connection_deleted", connection_id=str(connection_id))


# ---------------------------------------------------------------------------
# Browse Drive contents
# ---------------------------------------------------------------------------


@router.get("/browse", response_model=GDriveBrowseResponse)
async def browse_drive(
    connection_id: UUID = Query(...),
    folder_id: str = Query(default="root"),
    page_token: str | None = Query(default=None),
    page_size: int = Query(default=50, ge=1, le=1000),
    current_user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
    db: AsyncSession = Depends(get_db),
) -> GDriveBrowseResponse:
    """Browse files and folders in a connected Google Drive."""
    service = _get_gdrive_service()
    tokens_json = await service.get_connection_tokens(db, connection_id, matter_id)
    result = service.list_files(tokens_json, folder_id, page_token, page_size)
    return GDriveBrowseResponse(
        files=[GDriveFileItem(**f) for f in result["files"]],
        next_page_token=result["next_page_token"],
    )


# ---------------------------------------------------------------------------
# Ingest files from Drive
# ---------------------------------------------------------------------------


@router.post("/ingest", response_model=GDriveIngestResponse)
async def ingest_from_drive(
    body: GDriveIngestRequest,
    current_user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
    db: AsyncSession = Depends(get_db),
) -> GDriveIngestResponse:
    """Select files/folders from Drive and dispatch ingestion tasks."""
    from app.gdrive.tasks import sync_gdrive_folder

    service = _get_gdrive_service()

    # Verify connection exists and belongs to this matter
    tokens_json = await service.get_connection_tokens(db, body.connection_id, matter_id)

    # Collect all file IDs (resolve folders recursively)
    all_files: list[dict] = []
    for fid in body.file_ids:
        all_files.append({"id": fid, "name": fid, "mime_type": "unknown", "modified_time": None})

    for folder_id in body.folder_ids:
        folder_files = service.list_files_recursive(tokens_json, folder_id)
        all_files.extend(folder_files)

    if not all_files:
        raise HTTPException(status_code=400, detail="No files selected for ingestion")

    # Create a parent job
    from sqlalchemy import text

    result = await db.execute(
        text(
            """
            INSERT INTO jobs (id, filename, status, stage, matter_id, dataset_id, metadata_, created_at, updated_at)
            VALUES (gen_random_uuid(), :filename, 'processing', 'uploading', :matter_id, :dataset_id,
                    :metadata_, now(), now())
            RETURNING id
            """
        ),
        {
            "filename": f"gdrive-import-{len(all_files)}-files",
            "matter_id": str(matter_id),
            "dataset_id": str(body.dataset_id) if body.dataset_id else None,
            "metadata_": "{}",
        },
    )
    job_row = result.first()
    assert job_row is not None
    job_id = job_row.id

    # Dispatch Celery task
    sync_gdrive_folder.delay(
        job_id=str(job_id),
        connection_id=str(body.connection_id),
        matter_id=str(matter_id),
        file_ids=[f["id"] for f in all_files],
        dataset_id=str(body.dataset_id) if body.dataset_id else None,
    )

    logger.info("gdrive.ingest_dispatched", job_id=str(job_id), file_count=len(all_files))
    return GDriveIngestResponse(
        job_id=job_id,
        file_count=len(all_files),
        message=f"Dispatched ingestion for {len(all_files)} files",
    )


# ---------------------------------------------------------------------------
# Sync status
# ---------------------------------------------------------------------------


@router.get("/sync-status", response_model=GDriveSyncStatusResponse)
async def get_sync_status(
    connection_id: UUID = Query(...),
    current_user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
    db: AsyncSession = Depends(get_db),
) -> GDriveSyncStatusResponse:
    """Check the incremental sync state for a connection."""
    service = _get_gdrive_service()
    items = await service.get_sync_state(db, connection_id, matter_id)
    return GDriveSyncStatusResponse(
        connection_id=connection_id,
        items=[GDriveSyncStateItem(**item) for item in items],
        total=len(items),
    )


@router.post("/sync", response_model=GDriveIngestResponse)
async def sync_drive(
    body: GDriveSyncRequest,
    current_user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
    db: AsyncSession = Depends(get_db),
) -> GDriveIngestResponse:
    """Re-sync a previously imported connection (incremental)."""
    from app.gdrive.tasks import sync_gdrive_folder

    service = _get_gdrive_service()

    # Verify connection
    await service.get_connection_tokens(db, body.connection_id, matter_id)

    # Get existing sync map to find what we've previously imported
    sync_map = await service.get_existing_sync_map(db, body.connection_id)
    file_ids = list(sync_map.keys())

    if not file_ids:
        raise HTTPException(status_code=400, detail="No previously synced files to re-sync")

    # Create job
    from sqlalchemy import text

    result = await db.execute(
        text(
            """
            INSERT INTO jobs (id, filename, status, stage, matter_id, metadata_, created_at, updated_at)
            VALUES (gen_random_uuid(), :filename, 'processing', 'uploading', :matter_id, '{}', now(), now())
            RETURNING id
            """
        ),
        {
            "filename": f"gdrive-resync-{len(file_ids)}-files",
            "matter_id": str(matter_id),
        },
    )
    job_row = result.first()
    assert job_row is not None
    job_id = job_row.id

    sync_gdrive_folder.delay(
        job_id=str(job_id),
        connection_id=str(body.connection_id),
        matter_id=str(matter_id),
        file_ids=file_ids,
        dataset_id=None,
    )

    return GDriveIngestResponse(
        job_id=job_id,
        file_count=len(file_ids),
        message=f"Dispatched re-sync for {len(file_ids)} files",
    )
