"""External task tracking API endpoints.

POST   /scripts/tasks             — Register a new script task
PATCH  /scripts/tasks/{task_id}   — Update progress
GET    /scripts/tasks             — List tasks (paginated)
GET    /scripts/tasks/{task_id}   — Get single task
"""

from __future__ import annotations

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.middleware import get_current_user
from app.auth.schemas import UserRecord
from app.dependencies import get_db
from app.scripts.schemas import (
    ExternalTaskListResponse,
    ExternalTaskRegisterRequest,
    ExternalTaskResponse,
    ExternalTaskUpdateRequest,
)
from app.scripts.service import ExternalTaskService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/scripts", tags=["scripts"])


@router.post("/tasks", response_model=ExternalTaskResponse, status_code=201)
async def register_task(
    body: ExternalTaskRegisterRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(get_current_user),
):
    """Register a new external script as a tracked task."""
    row = await ExternalTaskService.register(
        db=db,
        name=body.name,
        script_name=body.script_name,
        total=body.total,
        metadata_=body.metadata_,
        matter_id=body.matter_id,
    )
    logger.info("external_task.registered", task_id=str(row["id"]), name=body.name)
    return ExternalTaskResponse(**row)


@router.patch("/tasks/{task_id}", response_model=ExternalTaskResponse)
async def update_task(
    task_id: UUID,
    body: ExternalTaskUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(get_current_user),
):
    """Update progress on an external task."""
    row = await ExternalTaskService.update(
        db=db,
        task_id=task_id,
        processed=body.processed,
        failed=body.failed,
        error=body.error,
        status=body.status,
        total=body.total,
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"External task {task_id} not found")
    return ExternalTaskResponse(**row)


@router.get("/tasks", response_model=ExternalTaskListResponse)
async def list_tasks(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    status: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(get_current_user),
):
    """List all external tasks (paginated)."""
    items, total = await ExternalTaskService.list_tasks(db=db, offset=offset, limit=limit, status=status)
    return ExternalTaskListResponse(items=items, total=total)


@router.get("/tasks/{task_id}", response_model=ExternalTaskResponse)
async def get_task(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(get_current_user),
):
    """Get a single external task."""
    row = await ExternalTaskService.get_task(db=db, task_id=task_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"External task {task_id} not found")
    return ExternalTaskResponse(**row)
