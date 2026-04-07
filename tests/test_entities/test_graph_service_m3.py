"""Tests for M3 graph_service methods (merge, search)."""

from __future__ import annotations

from datetime import UTC, datetime
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
    """merge_entities should execute a write query and return True on success."""
    graph_service._run_write_returning = AsyncMock(
        return_value=[{"merged_name": "Jeffrey Epstein"}],
    )

    result = await graph_service.merge_entities(
        canonical_name="Jeffrey Epstein",
        alias_name="J. Epstein",
        entity_type="person",
        matter_id="matter-1",
    )

    assert result is True
    graph_service._run_write_returning.assert_called_once()
    call_args = graph_service._run_write_returning.call_args
    params = call_args[0][1]
    assert params["canonical_name"] == "Jeffrey Epstein"
    assert params["alias_name"] == "J. Epstein"
    assert params["entity_type"] == "person"
    assert params["matter_id"] == "matter-1"


@pytest.mark.asyncio
async def test_merge_entities_cypher_uses_apoc(graph_service):
    """The merge query should use APOC mergeNodes for atomic relationship transfer."""
    graph_service._run_write_returning = AsyncMock(
        return_value=[{"merged_name": "A"}],
    )

    await graph_service.merge_entities("A", "B", "person", matter_id="m1")

    cypher = graph_service._run_write_returning.call_args[0][0]
    assert "apoc.refactor.mergeNodes" in cypher
    assert "mergeRels: true" in cypher
    assert "aliases" in cypher
    assert "matter_id" in cypher


@pytest.mark.asyncio
async def test_merge_entities_node_missing(graph_service):
    """merge_entities returns False when either node is not found."""
    graph_service._run_write_returning = AsyncMock(return_value=[])

    result = await graph_service.merge_entities("A", "B", "person", matter_id="m1")

    assert result is False


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
async def test_get_entity_connections_filters_out_none_targets(graph_service):
    """Connections with no displayable name (target=None) should be excluded."""
    graph_service._run_query = AsyncMock(
        return_value=[
            {
                "source": "Alice",
                "relationship_type": "KNOWS",
                "target": "Bob",
                "target_labels": ["Entity"],
                "edge_properties": {},
            },
            {
                "source": "Alice",
                "relationship_type": "MENTIONED_IN",
                "target": None,
                "target_labels": ["Chunk"],
                "edge_properties": {},
            },
        ]
    )

    records = await graph_service.get_entity_connections("Alice")
    assert len(records) == 1
    assert records[0]["target"] == "Bob"


@pytest.mark.asyncio
async def test_get_entity_connections_cypher_no_element_id_fallback(graph_service):
    """The Cypher query should not use toString(elementId(...)) as a COALESCE fallback."""
    graph_service._run_query = AsyncMock(return_value=[])

    await graph_service.get_entity_connections("Alice")

    cypher = graph_service._run_query.call_args[0][0]
    assert "elementId" not in cypher


@pytest.mark.asyncio
async def test_get_entity_connections_entity_only_true(graph_service):
    """entity_only=True should restrict Cypher MATCH to (connected:Entity)."""
    graph_service._run_query = AsyncMock(return_value=[])

    await graph_service.get_entity_connections("Alice", entity_only=True)

    cypher = graph_service._run_query.call_args[0][0]
    # The MATCH line should target Entity nodes only
    match_line = [line for line in cypher.splitlines() if "MATCH" in line][0]
    assert "(connected:Entity)" in match_line


@pytest.mark.asyncio
async def test_get_entity_connections_entity_only_false(graph_service):
    """entity_only=False (default) should match all node types."""
    graph_service._run_query = AsyncMock(return_value=[])

    await graph_service.get_entity_connections("Alice", entity_only=False)

    cypher = graph_service._run_query.call_args[0][0]
    match_line = [line for line in cypher.splitlines() if "MATCH" in line][0]
    assert "(connected)" in match_line
    assert "(connected:Entity)" not in match_line


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
async def test_get_entity_timeline_uses_document_date_not_created_at(graph_service):
    """Timeline Cypher must read d.document_date and NEVER fall back to created_at."""
    graph_service._run_query = AsyncMock(return_value=[])

    await graph_service.get_entity_timeline("Alice", matter_id="m-1")

    cypher = graph_service._run_query.call_args[0][0]
    assert "d.document_date" in cypher
    assert "d.created_at" not in cypher
    # No legacy coalesce fallback on d.date either
    assert "coalesce(d.date" not in cypher
    assert "d.document_date IS NOT NULL" in cypher


@pytest.mark.asyncio
async def test_get_entity_timeline_walks_email_path(graph_service):
    """Timeline must UNION MENTIONED_IN with SENT|SENT_TO|CC|BCC -> Email -> SOURCED_FROM path."""
    graph_service._run_query = AsyncMock(return_value=[])

    await graph_service.get_entity_timeline("Alice", matter_id="m-1")

    cypher = graph_service._run_query.call_args[0][0]
    assert "UNION" in cypher
    assert "MENTIONED_IN" in cypher
    assert "SENT|SENT_TO|CC|BCC" in cypher
    assert "SOURCED_FROM" in cypher


@pytest.mark.asyncio
async def test_get_entity_timeline_orders_by_document_date_desc(graph_service):
    """Timeline must order by document_date DESC so recent events appear first."""
    graph_service._run_query = AsyncMock(return_value=[])

    await graph_service.get_entity_timeline("Alice")

    cypher = graph_service._run_query.call_args[0][0]
    assert "ORDER BY d.document_date DESC" in cypher


@pytest.mark.asyncio
async def test_create_document_node_with_document_date(graph_service):
    """create_document_node should SET d.document_date from an ISO string."""
    graph_service._run_write = AsyncMock()

    await graph_service.create_document_node(
        doc_id="doc-1",
        filename="email.eml",
        doc_type="email",
        page_count=1,
        minio_path="raw/1/email.eml",
        matter_id="m-1",
        document_date=datetime(2020, 3, 15, 10, 0, 0, tzinfo=UTC),
    )

    call_args = graph_service._run_write.call_args
    cypher = call_args[0][0]
    params = call_args[0][1]
    assert "d.document_date = $document_date" in cypher
    assert params["document_date"] == "2020-03-15T10:00:00+00:00"
    # created_at must still be set separately for auditability
    assert "d.created_at    = datetime()" in cypher


@pytest.mark.asyncio
async def test_create_document_node_null_document_date(graph_service):
    """Omitted document_date should bind None (not a string)."""
    graph_service._run_write = AsyncMock()

    await graph_service.create_document_node(
        doc_id="doc-1",
        filename="scan.pdf",
        doc_type="pdf",
        page_count=3,
        minio_path="raw/1/scan.pdf",
        matter_id="m-1",
    )

    params = graph_service._run_write.call_args[0][1]
    assert params["document_date"] is None


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
