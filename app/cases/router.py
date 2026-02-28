"""Case intelligence API endpoints.

POST /cases/{matter_id}/setup    -- upload anchor doc, start case setup
GET  /cases/{matter_id}/context  -- get full case context
PATCH /cases/{matter_id}/context -- edit/confirm extracted context
"""

from __future__ import annotations

import json
from uuid import UUID, uuid4

import structlog
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.middleware import get_current_user, get_matter_id, require_role
from app.cases.schemas import (
    CaseContextResponse,
    CaseContextUpdateRequest,
    CaseSetupResponse,
    ClaimResponse,
    DefinedTermResponse,
    PartyResponse,
    TimelineEvent,
)
from app.cases.service import CaseService
from app.dependencies import get_db, get_minio

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["cases"])


def _parse_jsonb(val):
    """Safely parse a JSONB column that may be a string, list, or None."""
    if val is None:
        return []
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        try:
            parsed = json.loads(val)
            return list(parsed) if isinstance(parsed, list) else []
        except (json.JSONDecodeError, TypeError):
            return []
    return []


def _context_dict_to_response(ctx: dict) -> CaseContextResponse:
    """Convert a raw context dict (from CaseService.get_full_context) to response."""
    claims = [
        ClaimResponse(
            id=c["id"],
            claim_number=c["claim_number"],
            claim_label=c["claim_label"],
            claim_text=c["claim_text"],
            legal_elements=_parse_jsonb(c.get("legal_elements")),
            source_pages=_parse_jsonb(c.get("source_pages")),
        )
        for c in ctx.get("claims", [])
    ]

    parties = [
        PartyResponse(
            id=p["id"],
            name=p["name"],
            role=p["role"],
            description=p.get("description"),
            aliases=_parse_jsonb(p.get("aliases")),
            entity_id=p.get("entity_id"),
            source_pages=_parse_jsonb(p.get("source_pages")),
        )
        for p in ctx.get("parties", [])
    ]

    defined_terms = [
        DefinedTermResponse(
            id=t["id"],
            term=t["term"],
            definition=t["definition"],
            entity_id=t.get("entity_id"),
            source_pages=_parse_jsonb(t.get("source_pages")),
        )
        for t in ctx.get("defined_terms", [])
    ]

    timeline_raw = ctx.get("timeline", [])
    timeline = [
        TimelineEvent(
            date=e.get("date", ""),
            event_text=e.get("event_text", ""),
            source_page=e.get("source_page"),
        )
        for e in (timeline_raw if isinstance(timeline_raw, list) else [])
    ]

    return CaseContextResponse(
        id=ctx["id"],
        matter_id=ctx["matter_id"],
        status=ctx["status"],
        anchor_document_id=ctx["anchor_document_id"],
        claims=claims,
        parties=parties,
        defined_terms=defined_terms,
        timeline=timeline,
        created_at=ctx["created_at"],
        updated_at=ctx["updated_at"],
    )


# -----------------------------------------------------------------------
# POST /cases/{matter_id}/setup
# -----------------------------------------------------------------------


@router.post("/cases/{matter_id}/setup", response_model=CaseSetupResponse)
async def setup_case(
    matter_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_role("admin", "attorney")),
    user_matter_id: UUID = Depends(get_matter_id),
):
    """Upload an anchor document (complaint) and start case context extraction.

    Creates a job record and a case_contexts row, then dispatches the
    ``run_case_setup`` Celery task.
    """
    # Validate the path matter_id matches the header matter_id
    if matter_id != user_matter_id:
        raise HTTPException(
            status_code=403,
            detail="Path matter_id does not match X-Matter-ID header",
        )

    # Check if context already exists for this matter
    existing = await CaseService.get_case_context(db, str(matter_id))
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail="Case context already exists for this matter. Use PATCH to update.",
        )

    # Read and upload file to MinIO
    file_bytes = await file.read()
    filename = file.filename or "complaint"

    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    storage = get_minio()
    job_id = str(uuid4())
    minio_path = f"raw/{job_id}/{filename}"
    content_type = file.content_type or "application/octet-stream"
    await storage.upload_bytes(key=minio_path, data=file_bytes, content_type=content_type)

    # Create job record
    from app.ingestion.service import IngestionService

    job_row = await IngestionService.create_job(
        db=db,
        filename=filename,
        minio_path=minio_path,
        job_id=UUID(job_id),
        matter_id=matter_id,
    )

    # Create case context record
    ctx = await CaseService.create_case_context(
        db=db,
        matter_id=str(matter_id),
        anchor_document_id=minio_path,
        created_by=str(current_user["id"]),
        job_id=job_id,
    )

    await db.commit()

    # Dispatch Celery task
    from app.cases.tasks import run_case_setup

    run_case_setup.delay(
        job_id=str(job_row["id"]),
        case_context_id=str(ctx["id"]),
        matter_id=str(matter_id),
        minio_path=minio_path,
    )

    logger.info(
        "cases.setup_dispatched",
        job_id=str(job_row["id"]),
        case_context_id=str(ctx["id"]),
        matter_id=str(matter_id),
    )

    return CaseSetupResponse(
        job_id=str(job_row["id"]),
        case_context_id=str(ctx["id"]),
        status=ctx["status"],
        created_at=ctx["created_at"],
    )


# -----------------------------------------------------------------------
# GET /cases/{matter_id}/context
# -----------------------------------------------------------------------


@router.get("/cases/{matter_id}/context", response_model=CaseContextResponse)
async def get_case_context(
    matter_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    user_matter_id: UUID = Depends(get_matter_id),
):
    """Get the full case context for a matter."""
    if matter_id != user_matter_id:
        raise HTTPException(
            status_code=403,
            detail="Path matter_id does not match X-Matter-ID header",
        )

    ctx = await CaseService.get_full_context(db, str(matter_id))
    if ctx is None:
        raise HTTPException(status_code=404, detail="No case context found for this matter")

    return _context_dict_to_response(ctx)


# -----------------------------------------------------------------------
# PATCH /cases/{matter_id}/context
# -----------------------------------------------------------------------


@router.patch("/cases/{matter_id}/context", response_model=CaseContextResponse)
async def update_case_context(
    matter_id: UUID,
    body: CaseContextUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_role("admin", "attorney")),
    user_matter_id: UUID = Depends(get_matter_id),
):
    """Edit or confirm the extracted case context.

    Uses full-replace semantics: if claims/parties/terms are provided,
    the entire list is replaced.
    """
    if matter_id != user_matter_id:
        raise HTTPException(
            status_code=403,
            detail="Path matter_id does not match X-Matter-ID header",
        )

    ctx = await CaseService.get_case_context(db, str(matter_id))
    if ctx is None:
        raise HTTPException(status_code=404, detail="No case context found for this matter")

    context_id = str(ctx["id"])

    # Update status if provided
    if body.status is not None:
        confirmed_by = str(current_user["id"]) if body.status == "confirmed" else None
        await CaseService.update_case_context_status(
            db,
            context_id,
            body.status,
            confirmed_by=confirmed_by,
        )

    # Update claims if provided
    if body.claims is not None:
        claim_dicts = [c.model_dump() for c in body.claims]
        await CaseService.upsert_claims(db, context_id, claim_dicts)

    # Update parties if provided
    if body.parties is not None:
        party_dicts = [p.model_dump() for p in body.parties]
        await CaseService.upsert_parties(db, context_id, party_dicts)

    # Update defined terms if provided
    if body.defined_terms is not None:
        term_dicts = [t.model_dump() for t in body.defined_terms]
        await CaseService.upsert_defined_terms(db, context_id, term_dicts)

    # Update timeline if provided
    if body.timeline is not None:
        timeline_dicts = [e.model_dump() for e in body.timeline]
        await CaseService.update_timeline(db, context_id, timeline_dicts)

    await db.commit()

    # Return the updated full context
    updated = await CaseService.get_full_context(db, str(matter_id))
    return _context_dict_to_response(updated)
