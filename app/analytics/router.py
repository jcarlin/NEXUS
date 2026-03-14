"""Communication analytics API endpoints (M10c) + GraphRAG communities (T3-10).

GET  /analytics/communication-matrix     — pre-computed sender-recipient pairs
GET  /analytics/network-centrality       — Neo4j GDS centrality rankings
POST /analytics/communities/detect       — trigger community detection
GET  /analytics/communities              — list detected communities
GET  /analytics/communities/{id}         — get single community + related
"""

from __future__ import annotations

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
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
    from app.config import Settings

    settings = Settings()
    if not settings.enable_graph_centrality:
        raise HTTPException(
            status_code=501,
            detail="Graph centrality is not enabled. Set ENABLE_GRAPH_CENTRALITY=true.",
        )
    gs = get_graph_service()
    return await AnalyticsService.get_network_centrality(
        gs,
        str(matter_id),
        metric.value,
    )


# ------------------------------------------------------------------
# GraphRAG community endpoints (T3-10)
# ------------------------------------------------------------------


@router.post("/analytics/communities/detect", status_code=202)
async def detect_communities(
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
):
    """Trigger community detection via Neo4j GDS Louvain."""
    from app.config import Settings

    settings = Settings()
    if not settings.enable_graphrag_communities:
        raise HTTPException(
            status_code=501,
            detail="GraphRAG communities not enabled. Set ENABLE_GRAPHRAG_COMMUNITIES=true.",
        )

    from app.analytics.communities import CommunityDetector

    gs = get_graph_service()
    communities = await CommunityDetector.detect_communities(str(matter_id), gs)
    communities = CommunityDetector.build_hierarchy(communities)

    # Persist to DB
    await AnalyticsService.save_communities(db, str(matter_id), communities)

    return {"status": "completed", "community_count": len(communities)}


@router.get("/analytics/communities")
async def list_communities(
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
):
    """List detected communities for the current matter."""
    from app.config import Settings

    settings = Settings()
    if not settings.enable_graphrag_communities:
        raise HTTPException(
            status_code=501,
            detail="GraphRAG communities not enabled. Set ENABLE_GRAPHRAG_COMMUNITIES=true.",
        )

    communities = await AnalyticsService.list_communities(db, str(matter_id))
    return {"total": len(communities), "communities": communities}


@router.get("/analytics/communities/{community_id}")
async def get_community(
    community_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
):
    """Get a single community with related communities."""
    from app.config import Settings

    settings = Settings()
    if not settings.enable_graphrag_communities:
        raise HTTPException(
            status_code=501,
            detail="GraphRAG communities not enabled. Set ENABLE_GRAPHRAG_COMMUNITIES=true.",
        )

    community = await AnalyticsService.get_community(db, community_id, str(matter_id))
    if community is None:
        raise HTTPException(status_code=404, detail="Community not found.")

    related = await AnalyticsService.get_related_communities(db, community_id, str(matter_id))
    return {"community": community, "related_communities": related}
