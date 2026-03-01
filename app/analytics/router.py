"""Communication analytics API endpoints (M10c).

GET /analytics/communication-matrix  — pre-computed sender-recipient pairs
GET /analytics/network-centrality    — Neo4j GDS centrality rankings
"""

from __future__ import annotations

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.schemas import (
    CentralityMetric,
    CommunicationMatrixResponse,
    NetworkCentralityResponse,
)
from app.analytics.service import AnalyticsService
from app.auth.middleware import get_current_user, get_matter_id
from app.auth.schemas import UserRecord
from app.dependencies import get_db, get_graph_service

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["analytics"])


@router.get(
    "/analytics/communication-matrix",
    response_model=CommunicationMatrixResponse,
)
async def get_communication_matrix(
    entity_name: str | None = Query(None, description="Filter to pairs involving this entity"),
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
) -> CommunicationMatrixResponse:
    """Return the pre-computed communication matrix for the current matter."""
    return await AnalyticsService.get_communication_matrix(
        db,
        str(matter_id),
        entity_name=entity_name,
    )


@router.get(
    "/analytics/network-centrality",
    response_model=NetworkCentralityResponse,
)
async def get_network_centrality(
    metric: CentralityMetric = Query(CentralityMetric.DEGREE, description="Centrality algorithm"),
    current_user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
) -> NetworkCentralityResponse:
    """Return ranked entity centrality for the current matter."""
    gs = get_graph_service()
    return await AnalyticsService.get_network_centrality(
        gs,
        str(matter_id),
        metric.value,
    )
