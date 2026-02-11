"""Knowledge graph and entity API endpoints.

GET /entities                         -- search / list entities
GET /entities/{entity_id}             -- entity details + connections
GET /entities/{entity_id}/connections -- graph neighbourhood
GET /graph/explore                    -- interactive graph exploration (Cypher)
GET /graph/timeline/{entity}          -- chronological events for entity
GET /graph/stats                      -- graph statistics (node / edge counts)
"""

from fastapi import APIRouter

router = APIRouter(tags=["entities"])


@router.get("/entities")
async def list_entities():
    """Search or list extracted entities."""
    return {"detail": "not implemented"}


@router.get("/entities/{entity_id}")
async def get_entity(entity_id: str):
    """Return details and connections for a single entity."""
    return {"detail": "not implemented", "entity_id": entity_id}


@router.get("/entities/{entity_id}/connections")
async def get_entity_connections(entity_id: str):
    """Return the graph neighbourhood for an entity."""
    return {"detail": "not implemented", "entity_id": entity_id}


@router.get("/graph/explore")
async def graph_explore():
    """Interactive graph exploration via Cypher queries."""
    return {"detail": "not implemented"}


@router.get("/graph/timeline/{entity}")
async def graph_timeline(entity: str):
    """Return chronological events for an entity."""
    return {"detail": "not implemented", "entity": entity}


@router.get("/graph/stats")
async def graph_stats():
    """Return high-level graph statistics (node and edge counts)."""
    return {"detail": "not implemented"}
