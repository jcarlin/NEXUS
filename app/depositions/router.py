"""Deposition preparation API endpoints."""

from __future__ import annotations

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.middleware import get_current_user, get_matter_id
from app.auth.schemas import UserRecord
from app.dependencies import get_db, get_graph_service, get_llm
from app.depositions.schemas import (
    DepositionPrepRequest,
    DepositionPrepResponse,
    WitnessListResponse,
)
from app.depositions.service import DepositionService
from app.entities.graph_service import GraphService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/depositions", tags=["depositions"])


@router.get("/witnesses", response_model=WitnessListResponse)
async def list_witnesses(
    current_user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
    db: AsyncSession = Depends(get_db),
    graph_service: GraphService = Depends(get_graph_service),
) -> WitnessListResponse:
    """List all person entities as potential deposition witnesses."""
    witnesses, total = await DepositionService.list_witnesses(
        db=db,
        matter_id=matter_id,
        graph_service=graph_service,
    )
    return WitnessListResponse(witnesses=witnesses, total=total)


@router.post("/prep", response_model=DepositionPrepResponse)
async def generate_deposition_prep(
    body: DepositionPrepRequest,
    current_user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
    db: AsyncSession = Depends(get_db),
    graph_service: GraphService = Depends(get_graph_service),
) -> DepositionPrepResponse:
    """Generate a deposition preparation package for a witness."""
    llm = get_llm()
    return await DepositionService.generate_prep_package(
        db=db,
        matter_id=matter_id,
        witness_name=body.witness_name,
        graph_service=graph_service,
        llm=llm,
        max_questions=body.max_questions,
        focus_categories=body.focus_categories,
    )
