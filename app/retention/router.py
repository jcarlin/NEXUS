"""Retention policy API endpoints.

POST   /retention/policies                  -- create retention policy
GET    /retention/policies                  -- list all policies
GET    /retention/policies/{matter_id}      -- get policy by matter
DELETE /retention/policies/{matter_id}      -- remove active policy
POST   /retention/policies/{matter_id}/purge -- trigger manual purge
"""

from __future__ import annotations

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.middleware import require_role
from app.auth.schemas import UserRecord
from app.dependencies import get_db, get_minio, get_neo4j, get_qdrant
from app.retention.schemas import (
    RetentionPolicyListResponse,
    RetentionPolicyRequest,
    RetentionPolicyResponse,
)
from app.retention.service import RetentionService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/retention", tags=["retention"])


@router.post("/policies", response_model=RetentionPolicyResponse)
async def create_policy(
    body: RetentionPolicyRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(require_role("admin")),
):
    """Create a retention policy for a matter."""
    existing = await RetentionService.get_policy(db, body.matter_id)
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail="Retention policy already exists for this matter",
        )

    policy = await RetentionService.create_policy(
        db=db,
        matter_id=body.matter_id,
        retention_days=body.retention_days,
        user_id=current_user.id,
    )
    await db.commit()
    return RetentionPolicyResponse(**policy)


@router.get("/policies", response_model=RetentionPolicyListResponse)
async def list_policies(
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(require_role("admin")),
):
    """List all retention policies."""
    policies, total = await RetentionService.list_policies(db)
    return RetentionPolicyListResponse(
        policies=[RetentionPolicyResponse(**p) for p in policies],
        total=total,
    )


@router.get("/policies/{matter_id}", response_model=RetentionPolicyResponse)
async def get_policy(
    matter_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(require_role("admin")),
):
    """Get retention policy for a matter."""
    policy = await RetentionService.get_policy(db, matter_id)
    if policy is None:
        raise HTTPException(status_code=404, detail="No retention policy found for this matter")
    return RetentionPolicyResponse(**policy)


@router.delete("/policies/{matter_id}", status_code=200)
async def delete_policy(
    matter_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(require_role("admin")),
):
    """Delete an active retention policy."""
    policy = await RetentionService.get_policy(db, matter_id)
    if policy is None:
        raise HTTPException(status_code=404, detail="No retention policy found for this matter")

    if policy["status"] != "active":
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete policy with status '{policy['status']}' — only active policies can be deleted",
        )

    await RetentionService.delete_policy(db, matter_id)
    await db.commit()
    return {"detail": "Policy deleted"}


@router.post("/policies/{matter_id}/purge")
async def trigger_purge(
    matter_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(require_role("admin")),
):
    """Manually trigger purge for a matter."""
    policy = await RetentionService.get_policy(db, matter_id)
    if policy is None:
        raise HTTPException(status_code=404, detail="No retention policy found for this matter")

    qdrant = get_qdrant()
    neo4j_driver = get_neo4j()
    minio = get_minio()

    result = await RetentionService.execute_purge(
        db=db,
        matter_id=matter_id,
        qdrant_client=qdrant,
        neo4j_driver=neo4j_driver,
        minio_client=minio,
    )
    return result
