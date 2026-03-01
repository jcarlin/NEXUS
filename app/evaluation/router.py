"""Evaluation API endpoints.

GET    /evaluation/latest                    -- latest eval metrics
GET    /evaluation/datasets/{type}           -- list dataset items
POST   /evaluation/datasets/{type}           -- create dataset item
DELETE /evaluation/datasets/{type}/{item_id} -- delete dataset item
GET    /evaluation/runs                      -- list runs
POST   /evaluation/runs                      -- trigger new run
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.middleware import require_role
from app.auth.schemas import UserRecord
from app.dependencies import get_db
from app.evaluation.schemas import (
    DatasetItemCreate,
    DatasetItemListResponse,
    DatasetItemResponse,
    DatasetType,
    EvalRunListResponse,
    EvalRunResponse,
    LatestEvalResponse,
    RunCreateRequest,
)
from app.evaluation.service import EvaluationService

router = APIRouter(prefix="/evaluation", tags=["evaluation"])


@router.get("/latest", response_model=LatestEvalResponse)
async def get_latest_eval(
    db: AsyncSession = Depends(get_db),
    _user: UserRecord = Depends(require_role("admin")),
) -> LatestEvalResponse:
    """Return metrics from the most recent completed evaluation run."""
    latest = await EvaluationService.get_latest(db)
    if not latest:
        raise HTTPException(status_code=404, detail="No completed evaluation runs found")
    return latest


@router.get("/datasets/{dataset_type}", response_model=DatasetItemListResponse)
async def list_dataset_items(
    dataset_type: DatasetType,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _user: UserRecord = Depends(require_role("admin")),
) -> DatasetItemListResponse:
    """List items in a specific evaluation dataset."""
    items, total = await EvaluationService.list_dataset_items(db, dataset_type, offset, limit)
    return DatasetItemListResponse(items=items, total=total, offset=offset, limit=limit)


@router.post("/datasets/{dataset_type}", response_model=DatasetItemResponse, status_code=201)
async def create_dataset_item(
    dataset_type: DatasetType,
    item: DatasetItemCreate,
    db: AsyncSession = Depends(get_db),
    _user: UserRecord = Depends(require_role("admin")),
) -> DatasetItemResponse:
    """Add a new item to an evaluation dataset."""
    result = await EvaluationService.create_dataset_item(db, dataset_type, item)
    await db.commit()
    return result


@router.delete("/datasets/{dataset_type}/{item_id}", status_code=204)
async def delete_dataset_item(
    dataset_type: DatasetType,
    item_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: UserRecord = Depends(require_role("admin")),
):
    """Remove an item from an evaluation dataset."""
    deleted = await EvaluationService.delete_dataset_item(db, item_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Dataset item not found")
    await db.commit()


@router.get("/runs", response_model=EvalRunListResponse)
async def list_runs(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _user: UserRecord = Depends(require_role("admin")),
) -> EvalRunListResponse:
    """List all evaluation runs."""
    items, total = await EvaluationService.list_runs(db, offset, limit)
    return EvalRunListResponse(items=items, total=total, offset=offset, limit=limit)


@router.post("/runs", response_model=EvalRunResponse, status_code=201)
async def create_run(
    request: RunCreateRequest,
    db: AsyncSession = Depends(get_db),
    _user: UserRecord = Depends(require_role("admin")),
) -> EvalRunResponse:
    """Trigger a new evaluation run."""
    run = await EvaluationService.create_run(db, request.mode, request.config_overrides)
    await db.commit()
    return run
