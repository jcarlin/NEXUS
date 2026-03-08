"""Knowledge graph and entity API endpoints.

GET /entities                         -- search / list entities
GET /entities/{entity_id}             -- entity details + connections
GET /entities/{entity_id}/connections -- graph neighbourhood
GET /graph/explore                    -- interactive graph exploration (Cypher)
GET /graph/timeline/{entity}          -- chronological events for entity
GET /graph/stats                      -- graph statistics (node / edge counts)
"""

import re
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth.middleware import get_current_user, get_matter_id
from app.auth.schemas import UserRecord
from app.dependencies import get_graph_service
from app.entities.graph_service import GraphService

router = APIRouter(tags=["entities"])

# Dangerous Cypher keywords that could mutate the graph
_CYPHER_WRITE_RE = re.compile(
    r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|CALL)\b",
    re.IGNORECASE,
)


@router.get("/entities")
async def list_entities(
    q: str | None = Query(None, description="Search query for entity name"),
    entity_type: str | None = Query(None, description="Filter by entity type"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    gs: GraphService = Depends(get_graph_service),
    current_user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
):
    """Search or list extracted entities (paginated)."""
    items, total = await gs.search_entities(
        query=q, entity_type=entity_type, limit=limit, offset=offset, matter_id=str(matter_id)
    )
    return {
        "items": items,
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.get("/entities/connections")
async def get_entity_connections_by_query(
    name: str = Query(..., description="Entity name"),
    limit: int = Query(50, ge=1, le=200),
    gs: GraphService = Depends(get_graph_service),
    current_user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
):
    """Return the graph neighbourhood for an entity (query-param lookup).

    Preferred over the path-param variant because entity names may contain
    slashes or other characters that break URL routing.
    """
    entity = await gs.get_entity_by_name(name, matter_id=str(matter_id))
    if entity is None:
        raise HTTPException(status_code=404, detail=f"Entity '{name}' not found")
    exclude_privilege = ["privileged", "work_product"] if current_user.role not in ("admin", "attorney") else None
    connections = await gs.get_entity_connections(
        name,
        limit=limit,
        exclude_privilege_statuses=exclude_privilege,
        matter_id=str(matter_id),
    )
    return {"entity": entity, "connections": connections}


@router.get("/entities/{entity_id}")
async def get_entity(
    entity_id: str,
    gs: GraphService = Depends(get_graph_service),
    current_user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
):
    """Return details for a single entity (looked up by name)."""
    entity = await gs.get_entity_by_name(entity_id, matter_id=str(matter_id))
    if entity is None:
        raise HTTPException(status_code=404, detail=f"Entity '{entity_id}' not found")
    return entity


@router.get("/entities/{entity_id}/connections")
async def get_entity_connections(
    entity_id: str,
    limit: int = Query(50, ge=1, le=200),
    gs: GraphService = Depends(get_graph_service),
    current_user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
):
    """Return the graph neighbourhood for an entity (path-param variant).

    Note: entity names containing slashes will fail with this endpoint.
    Prefer ``GET /entities/connections?name=...`` instead.
    """
    entity = await gs.get_entity_by_name(entity_id, matter_id=str(matter_id))
    if entity is None:
        raise HTTPException(status_code=404, detail=f"Entity '{entity_id}' not found")
    exclude_privilege = ["privileged", "work_product"] if current_user.role not in ("admin", "attorney") else None
    connections = await gs.get_entity_connections(
        entity_id,
        limit=limit,
        exclude_privilege_statuses=exclude_privilege,
        matter_id=str(matter_id),
    )
    return {"entity": entity, "connections": connections}


@router.get("/graph/explore")
async def graph_explore(
    cypher: str = Query(..., description="Read-only Cypher query"),
    gs: GraphService = Depends(get_graph_service),
    current_user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
):
    """Interactive graph exploration via Cypher queries.

    Only read-only queries are allowed. Queries containing CREATE, MERGE,
    DELETE, SET, REMOVE, DROP, or CALL are rejected.
    """
    if _CYPHER_WRITE_RE.search(cypher):
        raise HTTPException(
            status_code=400,
            detail="Write operations are not allowed via the explore endpoint. "
            "Only read-only MATCH/RETURN queries are permitted.",
        )
    try:
        records = await gs._run_query(cypher, {"matter_id": str(matter_id)})
        return {"results": records}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Cypher query error: {exc}")


@router.get("/graph/timeline/{entity}")
async def graph_timeline(
    entity: str,
    gs: GraphService = Depends(get_graph_service),
    current_user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
):
    """Return chronological events for an entity."""
    events = await gs.get_entity_timeline(entity, matter_id=str(matter_id))
    return {"entity": entity, "events": events}


@router.get("/graph/stats")
async def graph_stats(
    gs: GraphService = Depends(get_graph_service),
    current_user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
):
    """Return high-level graph statistics (node and edge counts)."""
    stats = await gs.get_graph_stats(matter_id=str(matter_id))
    return stats


@router.get("/graph/communication-pairs")
async def communication_pairs(
    person_a: str = Query(..., description="First person name"),
    person_b: str = Query(..., description="Second person name"),
    date_from: str | None = Query(None, description="Start date filter (YYYY-MM-DD)"),
    date_to: str | None = Query(None, description="End date filter (YYYY-MM-DD)"),
    gs: GraphService = Depends(get_graph_service),
    current_user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
):
    """Return emails exchanged between two people."""
    emails = await gs.get_communication_pairs(
        person_a,
        person_b,
        date_from,
        date_to,
        matter_id=str(matter_id),
    )
    return {
        "person_a": person_a,
        "person_b": person_b,
        "emails": emails,
        "total": len(emails),
    }


@router.get("/graph/reporting-chain/{person}")
async def reporting_chain(
    person: str,
    date: str | None = Query(None, description="Point-in-time filter (YYYY-MM-DD)"),
    gs: GraphService = Depends(get_graph_service),
    current_user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
):
    """Return the REPORTS_TO chain for a person."""
    chains = await gs.get_reporting_chain(person, date, matter_id=str(matter_id))
    return {"person": person, "chains": chains}


@router.get("/graph/path")
async def graph_path(
    entity_a: str = Query(..., description="Start entity name"),
    entity_b: str = Query(..., description="End entity name"),
    max_hops: int = Query(5, ge=1, le=10, description="Maximum path length"),
    relationship_types: str | None = Query(None, description="Comma-separated relationship types"),
    gs: GraphService = Depends(get_graph_service),
    current_user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
):
    """Find shortest path between two entities."""
    rel_types = [t.strip() for t in relationship_types.split(",")] if relationship_types else None
    paths = await gs.find_path(
        entity_a,
        entity_b,
        max_hops,
        rel_types,
        matter_id=str(matter_id),
    )
    return {"entity_a": entity_a, "entity_b": entity_b, "paths": paths}
