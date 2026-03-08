"""Memo drafting API endpoints."""

from __future__ import annotations

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.middleware import get_current_user, get_matter_id
from app.auth.schemas import UserRecord
from app.dependencies import get_db, get_llm
from app.memos.schemas import MemoListResponse, MemoRequest, MemoResponse
from app.memos.service import MemoService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/memos", tags=["memos"])


@router.post("", response_model=MemoResponse, status_code=201)
async def create_memo(
    body: MemoRequest,
    current_user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
    db: AsyncSession = Depends(get_db),
):
    """Generate a legal memo from a chat thread or ad-hoc query."""
    # Validate: must provide thread_id or query
    if not body.thread_id and not body.query:
        raise HTTPException(status_code=422, detail="Either thread_id or query is required")

    llm = get_llm()
    memo = await MemoService.generate_memo(
        db=db,
        matter_id=matter_id,
        user_id=current_user.id,
        llm=llm,
        thread_id=body.thread_id,
        query=body.query,
        title=body.title,
        memo_format=body.format,
        include_source_index=body.include_source_index,
    )
    return memo


@router.get("", response_model=MemoListResponse)
async def list_memos(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
    db: AsyncSession = Depends(get_db),
):
    """List memos for the current matter."""
    memos, total = await MemoService.list_memos(db, matter_id, limit, offset)
    return MemoListResponse(items=memos, total=total)


@router.get("/{memo_id}", response_model=MemoResponse)
async def get_memo(
    memo_id: UUID,
    current_user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific memo."""
    memo = await MemoService.get_memo(db, memo_id, matter_id)
    if memo is None:
        raise HTTPException(status_code=404, detail="Memo not found")
    return memo


@router.delete("/{memo_id}", status_code=204)
async def delete_memo(
    memo_id: UUID,
    current_user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
    db: AsyncSession = Depends(get_db),
):
    """Delete a memo."""
    deleted = await MemoService.delete_memo(db, memo_id, matter_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Memo not found")
