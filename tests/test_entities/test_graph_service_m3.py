"""Tests for M3 graph_service methods (merge, search)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.entities.graph_service import GraphService


@pytest.fixture
def mock_driver():
    """Create a mock Neo4j AsyncDriver."""
    driver = AsyncMock()
    return driver


@pytest.fixture
def graph_service(mock_driver):
    """Create a GraphService with a mocked driver."""
    return GraphService(mock_driver)


@pytest.mark.asyncio
async def test_merge_entities(graph_service):
    """merge_entities should execute a write query."""
    graph_service._run_write = AsyncMock()

    await graph_service.merge_entities(
        canonical_name="Jeffrey Epstein",
        alias_name="J. Epstein",
        entity_type="person",
        matter_id="matter-1",
    )

    graph_service._run_write.assert_called_once()
    call_args = graph_service._run_write.call_args
    params = call_args[0][1]
    assert params["canonical_name"] == "Jeffrey Epstein"
    assert params["alias_name"] == "J. Epstein"
    assert params["entity_type"] == "person"
    assert params["matter_id"] == "matter-1"


@pytest.mark.asyncio
async def test_merge_entities_cypher_structure(graph_service):
    """The merge query should contain DETACH DELETE for the alias node."""
    graph_service._run_write = AsyncMock()

    await graph_service.merge_entities("A", "B", "person", matter_id="m1")

    cypher = graph_service._run_write.call_args[0][0]
    assert "DETACH DELETE" in cypher
    assert "MERGE" in cypher
    assert "aliases" in cypher
    assert "matter_id" in cypher


@pytest.mark.asyncio
async def test_search_entities(graph_service):
    """search_entities should return items and total count."""
    graph_service._run_query = AsyncMock(
        side_effect=[
            [{"total": 2}],  # count query
            [
                {
                    "name": "Alice",
                    "type": "person",
                    "mention_count": 5,
                    "first_seen": None,
                    "last_seen": None,
                    "aliases": [],
                },
                {
                    "name": "Bob",
                    "type": "person",
                    "mention_count": 3,
                    "first_seen": None,
                    "last_seen": None,
                    "aliases": [],
                },
            ],
        ]
    )

    items, total = await graph_service.search_entities(entity_type="person")
    assert total == 2
    assert len(items) == 2
    assert items[0]["name"] == "Alice"


@pytest.mark.asyncio
async def test_search_entities_with_query(graph_service):
    """search_entities with a text query should filter by name."""
    graph_service._run_query = AsyncMock(
        side_effect=[
            [{"total": 1}],
            [
                {
                    "name": "Alice",
                    "type": "person",
                    "mention_count": 5,
                    "first_seen": None,
                    "last_seen": None,
                    "aliases": [],
                }
            ],
        ]
    )

    items, total = await graph_service.search_entities(query="alice", entity_type="person")
    assert total == 1

    # Verify the query parameter was passed
    count_call_params = graph_service._run_query.call_args_list[0][0][1]
    assert count_call_params["query"] == "alice"


@pytest.mark.asyncio
async def test_search_entities_with_matter_id(graph_service):
    """search_entities with matter_id should include matter_id WHERE clause."""
    graph_service._run_query = AsyncMock(
        side_effect=[
            [{"total": 1}],
            [
                {
                    "name": "Alice",
                    "type": "person",
                    "mention_count": 5,
                    "first_seen": None,
                    "last_seen": None,
                    "aliases": [],
                }
            ],
        ]
    )

    items, total = await graph_service.search_entities(matter_id="m-123")
    assert total == 1

    # Verify matter_id was passed in params
    count_call_params = graph_service._run_query.call_args_list[0][0][1]
    assert count_call_params["matter_id"] == "m-123"
    # Verify the Cypher contains the matter_id filter
    count_cypher = graph_service._run_query.call_args_list[0][0][0]
    assert "matter_id" in count_cypher


@pytest.mark.asyncio
async def test_get_entity_by_name_with_matter_id(graph_service):
    """get_entity_by_name with matter_id should filter by matter."""
    graph_service._run_query = AsyncMock(
        return_value=[
            {
                "name": "Alice",
                "type": "person",
                "mention_count": 5,
                "first_seen": None,
                "last_seen": None,
                "aliases": [],
            }
        ]
    )

    result = await graph_service.get_entity_by_name("Alice", matter_id="m-123")
    assert result is not None
    assert result["name"] == "Alice"

    call_params = graph_service._run_query.call_args[0][1]
    assert call_params["matter_id"] == "m-123"
    cypher = graph_service._run_query.call_args[0][0]
    assert "matter_id" in cypher


@pytest.mark.asyncio
async def test_get_entity_connections_with_matter_id(graph_service):
    """get_entity_connections with matter_id should filter by matter."""
    graph_service._run_query = AsyncMock(return_value=[])

    await graph_service.get_entity_connections("Alice", matter_id="m-123")

    call_params = graph_service._run_query.call_args[0][1]
    assert call_params["matter_id"] == "m-123"
    cypher = graph_service._run_query.call_args[0][0]
    assert "matter_id" in cypher


@pytest.mark.asyncio
async def test_get_entity_timeline_with_matter_id(graph_service):
    """get_entity_timeline with matter_id should filter by matter."""
    graph_service._run_query = AsyncMock(return_value=[])

    await graph_service.get_entity_timeline("Alice", matter_id="m-123")

    call_params = graph_service._run_query.call_args[0][1]
    assert call_params["matter_id"] == "m-123"
    cypher = graph_service._run_query.call_args[0][0]
    assert "matter_id" in cypher


@pytest.mark.asyncio
async def test_get_graph_stats_with_matter_id(graph_service):
    """get_graph_stats with matter_id should scope counts to that matter."""
    graph_service._run_query = AsyncMock(
        side_effect=[
            [{"label": "Entity", "count": 10}],
            [{"type": "MENTIONED_IN", "count": 20}],
        ]
    )

    stats = await graph_service.get_graph_stats(matter_id="m-123")
    assert stats["total_nodes"] == 10
    assert stats["total_edges"] == 20

    # Both queries should receive matter_id
    for call in graph_service._run_query.call_args_list:
        assert call[0][1]["matter_id"] == "m-123"
        assert "matter_id" in call[0][0]
