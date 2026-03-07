"""Redaction API endpoints.

POST /documents/{document_id}/redact         -- apply redactions to a document
GET  /documents/{document_id}/redaction-log   -- view redaction audit log
GET  /documents/{document_id}/pii-detections  -- auto-detect PII in document
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.middleware import get_current_user, get_matter_id, require_role
from app.auth.schemas import UserRecord
from app.common.storage import StorageClient
from app.dependencies import get_db, get_minio
from app.redaction.schemas import (
    PIIDetection,
    RedactionLogEntry,
    RedactionLogResponse,
    RedactRequest,
    RedactResponse,
)
from app.redaction.service import RedactionService

router = APIRouter(tags=["redaction"])


def _require_redaction_enabled() -> None:
    """Dependency that rejects requests when redaction is disabled."""
    from app.config import Settings

    if not Settings().enable_redaction:
        raise HTTPException(
            status_code=501,
            detail="Redaction is not enabled. Set ENABLE_REDACTION=true.",
        )


# -----------------------------------------------------------------------
# POST /documents/{document_id}/redact — apply redactions
# -----------------------------------------------------------------------


@router.post(
    "/documents/{document_id}/redact",
    response_model=RedactResponse,
)
async def apply_redactions(
    document_id: UUID,
    body: RedactRequest,
    _flag: None = Depends(_require_redaction_enabled),
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(require_role("attorney", "admin")),
    matter_id: UUID = Depends(get_matter_id),
    storage: StorageClient = Depends(get_minio),
):
    """Apply a set of redactions to a document's PDF.

    Requires ``attorney`` or ``admin`` role.  Produces a permanently
    redacted PDF (text physically removed, not visually masked).
    """
    try:
        result = await RedactionService.apply_redactions(
            db=db,
            storage=storage,
            matter_id=matter_id,
            document_id=document_id,
            user_id=current_user.id,
            specs=body.redactions,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return RedactResponse(**result)


# -----------------------------------------------------------------------
# GET /documents/{document_id}/redaction-log — audit log
# -----------------------------------------------------------------------


@router.get(
    "/documents/{document_id}/redaction-log",
    response_model=RedactionLogResponse,
)
async def get_redaction_log(
    document_id: UUID,
    offset: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=200, description="Max records to return"),
    _flag: None = Depends(_require_redaction_enabled),
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
):
    """View the immutable redaction audit log for a document."""
    items, total = await RedactionService.get_redaction_log(
        db=db,
        matter_id=matter_id,
        document_id=document_id,
        offset=offset,
        limit=limit,
    )
    return RedactionLogResponse(
        items=[RedactionLogEntry(**row) for row in items],
        total=total,
        offset=offset,
        limit=limit,
    )


# -----------------------------------------------------------------------
# GET /documents/{document_id}/pii-detections — auto-detect PII
# -----------------------------------------------------------------------


@router.get(
    "/documents/{document_id}/pii-detections",
    response_model=list[PIIDetection],
)
async def detect_pii(
    document_id: UUID,
    _flag: None = Depends(_require_redaction_enabled),
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
):
    """Run PII auto-detection on document chunks and return suggestions."""
    try:
        detections = await RedactionService.detect_pii_for_document(
            db=db,
            matter_id=matter_id,
            document_id=document_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return detections
