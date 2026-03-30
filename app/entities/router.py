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

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from app.auth.middleware import get_current_user, get_matter_id, require_role
from app.auth.schemas import UserRecord
from app.dependencies import get_graph_service
from app.entities.graph_service import GraphService
from app.entities.schemas import (
    CommunicationPairsResponse,
    EntityMergeRequest,
    EntityRenameRequest,
    EntityTypeUpdateRequest,
    RelationshipCreateRequest,
    RelationshipDeleteRequest,
)

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
    entity_types: str | None = Query(None, description="Comma-separated entity types (overrides entity_type)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    gs: GraphService = Depends(get_graph_service),
    current_user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
):
    """Search or list extracted entities (paginated)."""
    types_list = [t.strip() for t in entity_types.split(",") if t.strip()] if entity_types else None
    items, total = await gs.search_entities(
        query=q,
        entity_type=entity_type,
        entity_types=types_list,
        limit=limit,
        offset=offset,
        matter_id=str(matter_id),
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
    entity_only: bool = Query(False, description="Only return connections to other Entity nodes"),
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
        entity_only=entity_only,
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
    entity_only: bool = Query(False, description="Only return connections to other Entity nodes"),
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
        entity_only=entity_only,
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


@router.get("/graph/communication-pairs", response_model=CommunicationPairsResponse)
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


# ---------------------------------------------------------------------------
# Interactive graph editing (T3-5) — require admin or attorney role
# ---------------------------------------------------------------------------


@router.patch("/matters/{matter_id}/entities/{name}/rename")
async def rename_entity(
    matter_id: UUID,
    name: str,
    body: EntityRenameRequest,
    gs: GraphService = Depends(get_graph_service),
    current_user: UserRecord = Depends(require_role("admin", "attorney")),
    _matter_id: UUID = Depends(get_matter_id),
):
    """Rename an entity node in the knowledge graph."""
    result = await gs.rename_entity(
        matter_id=str(matter_id),
        old_name=name,
        new_name=body.new_name,
    )
    if result is None:
        raise HTTPException(status_code=404, detail=f"Entity '{name}' not found")
    return result


@router.patch("/matters/{matter_id}/entities/{name}/type")
async def update_entity_type(
    matter_id: UUID,
    name: str,
    body: EntityTypeUpdateRequest,
    gs: GraphService = Depends(get_graph_service),
    current_user: UserRecord = Depends(require_role("admin", "attorney")),
    _matter_id: UUID = Depends(get_matter_id),
):
    """Update the type of an entity node."""
    result = await gs.update_entity_type(
        matter_id=str(matter_id),
        name=name,
        new_type=body.new_type,
    )
    if result is None:
        raise HTTPException(status_code=404, detail=f"Entity '{name}' not found")
    return result


@router.delete("/matters/{matter_id}/entities/{name}")
async def delete_entity(
    matter_id: UUID,
    name: str,
    gs: GraphService = Depends(get_graph_service),
    current_user: UserRecord = Depends(require_role("admin", "attorney")),
    _matter_id: UUID = Depends(get_matter_id),
):
    """Delete an entity and all its relationships."""
    deleted = await gs.delete_entity(
        matter_id=str(matter_id),
        name=name,
    )
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Entity '{name}' not found")
    return {"detail": f"Entity '{name}' deleted"}


@router.post("/matters/{matter_id}/entities/merge")
async def merge_entities(
    matter_id: UUID,
    body: EntityMergeRequest,
    gs: GraphService = Depends(get_graph_service),
    current_user: UserRecord = Depends(require_role("admin", "attorney")),
    _matter_id: UUID = Depends(get_matter_id),
):
    """Merge two entities (source is absorbed into target)."""
    if body.source_name == body.target_name:
        raise HTTPException(
            status_code=400,
            detail="Source and target entity names must be different",
        )

    # Check both entities exist
    source = await gs.get_entity_by_name(body.source_name, matter_id=str(matter_id))
    if source is None:
        raise HTTPException(status_code=404, detail=f"Source entity '{body.source_name}' not found")

    target = await gs.get_entity_by_name(body.target_name, matter_id=str(matter_id))
    if target is None:
        raise HTTPException(status_code=404, detail=f"Target entity '{body.target_name}' not found")

    await gs.merge_entities(
        canonical_name=body.target_name,
        alias_name=body.source_name,
        entity_type=source["type"],
        matter_id=str(matter_id),
    )
    return {"detail": f"Entity '{body.source_name}' merged into '{body.target_name}'"}


@router.post("/matters/{matter_id}/relationships")
async def create_relationship(
    matter_id: UUID,
    body: RelationshipCreateRequest,
    gs: GraphService = Depends(get_graph_service),
    current_user: UserRecord = Depends(require_role("admin", "attorney")),
    _matter_id: UUID = Depends(get_matter_id),
):
    """Create a new relationship between two entities."""
    result = await gs.create_relationship(
        matter_id=str(matter_id),
        source_name=body.source_name,
        target_name=body.target_name,
        relationship_type=body.relationship_type,
        properties=body.properties,
    )
    if result is None:
        raise HTTPException(
            status_code=404,
            detail="One or both entities not found",
        )
    return result


@router.delete("/matters/{matter_id}/relationships")
async def delete_relationship(
    matter_id: UUID,
    body: RelationshipDeleteRequest = Body(...),
    gs: GraphService = Depends(get_graph_service),
    current_user: UserRecord = Depends(require_role("admin", "attorney")),
    _matter_id: UUID = Depends(get_matter_id),
):
    """Delete a specific relationship between two entities."""
    deleted = await gs.delete_relationship(
        matter_id=str(matter_id),
        source_name=body.source_name,
        target_name=body.target_name,
        relationship_type=body.relationship_type,
    )
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail="Relationship or entities not found",
        )
    return {"detail": "Relationship deleted"}
