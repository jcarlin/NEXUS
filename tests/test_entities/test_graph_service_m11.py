"""Tests for M11 knowledge graph enhancements.

Covers:
- 9 core node types (dual-label validation)
- Email-as-node with SENT/SENT_TO/CC/BCC edges
- Temporal relationships (create, validate allowlist)
- Communication pairs query
- Reporting chain query
- Path finding
- Topic / DISCUSSES edges
- ALIAS_OF edges
- Batch entity lookup (Qdrant <-> Neo4j cross-ref)
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.entities.graph_service import GraphService
from app.entities.schema import (
    NODE_LABELS,
    get_neo4j_label,
    parse_email_address,
    parse_recipient_list,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_driver():
    """Create a mock Neo4j AsyncDriver."""
    return AsyncMock()


@pytest.fixture
def gs(mock_driver):
    """Create a GraphService with a mocked driver."""
    return GraphService(mock_driver)


# ---------------------------------------------------------------------------
# Step 3: Schema validation
# ---------------------------------------------------------------------------


def test_9_core_node_types_validation():
    """All 9 required node types exist in NODE_LABELS."""
    required = {
        "Entity",
        "Person",
        "Organization",
        "Location",
        "Event",
        "Financial",
        "LegalReference",
        "ContactInfo",
        "Email",
    }
    assert required.issubset(set(NODE_LABELS))


def test_entity_type_to_label_mapping():
    """Key GLiNER types should map to correct Neo4j labels."""
    assert get_neo4j_label("person") == "Person"
    assert get_neo4j_label("organization") == "Organization"
    assert get_neo4j_label("court") == "Organization"
    assert get_neo4j_label("date") == "Event"
    assert get_neo4j_label("money") == "Financial"
    assert get_neo4j_label("legal_reference") == "LegalReference"
    assert get_neo4j_label("email") == "ContactInfo"
    assert get_neo4j_label("unknown_type") is None


# ---------------------------------------------------------------------------
# Step 4: Dual-label entity creation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_entity_node_dual_label(gs):
    """create_entity_node should include a secondary label clause for known types."""
    gs._run_write = AsyncMock()

    await gs.create_entity_node(
        name="John Doe",
        entity_type="person",
        doc_id="doc-1",
        page_number=3,
        matter_id="matter-1",
    )

    gs._run_write.assert_called_once()
    cypher = gs._run_write.call_args[0][0]
    # Should contain secondary label
    assert "SET e:Person" in cypher
    # MERGE key should include matter_id
    assert "matter_id: $matter_id" in cypher
    # Should pass matter_id
    params = gs._run_write.call_args[0][1]
    assert params["matter_id"] == "matter-1"


@pytest.mark.asyncio
async def test_create_entity_node_unknown_type_no_label(gs):
    """Unknown entity types should not add a secondary label clause."""
    gs._run_write = AsyncMock()

    await gs.create_entity_node(
        name="Widget",
        entity_type="unknown_thing",
        doc_id="doc-2",
    )

    cypher = gs._run_write.call_args[0][0]
    # No secondary label for unknown types
    assert "SET e:" not in cypher or "SET e:Entity" not in cypher
    # MERGE key should still include matter_id
    assert "matter_id: $matter_id" in cypher


@pytest.mark.asyncio
async def test_index_entities_dual_labels(gs):
    """index_entities_for_document should group by type and apply correct labels."""
    gs._run_write = AsyncMock()

    entities = [
        {"name": "Alice", "type": "person", "page_number": 1},
        {"name": "Bob", "type": "person", "page_number": 2},
        {"name": "Acme Corp", "type": "organization", "page_number": 1},
    ]

    count = await gs.index_entities_for_document(
        doc_id="doc-1",
        entities=entities,
        matter_id="m1",
    )

    assert count == 3
    # Should have been called twice (once per type batch)
    assert gs._run_write.call_count == 2

    calls = gs._run_write.call_args_list
    cyphers = [c[0][0] for c in calls]

    # One batch should have :Person, the other :Organization
    labels_found = set()
    for cypher in cyphers:
        if "SET e:Person" in cypher:
            labels_found.add("Person")
        if "SET e:Organization" in cypher:
            labels_found.add("Organization")
    assert labels_found == {"Person", "Organization"}


# ---------------------------------------------------------------------------
# Step 5: Email-as-node
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_email_as_node_sent_to_cc_bcc(gs):
    """create_email_node + link_email_participants should create correct edges."""
    gs._run_write = AsyncMock()

    # Create email node
    await gs.create_email_node(
        email_id="msg-001",
        subject="Meeting notes",
        date="2024-01-15",
        message_id="<abc@example.com>",
        doc_id="doc-1",
        matter_id="matter-1",
    )

    # Check email node creation
    cypher = gs._run_write.call_args[0][0]
    assert "MERGE (em:Email" in cypher
    assert "SOURCED_FROM" in cypher

    gs._run_write.reset_mock()

    # Link participants
    await gs.link_email_participants(
        email_id="msg-001",
        sender=("John Doe", "john@example.com"),
        to=[("Jane Smith", "jane@example.com")],
        cc=[("Bob", "bob@example.com")],
        bcc=[("Charlie", "charlie@example.com")],
        matter_id="matter-1",
    )

    # Should have 4 _run_write calls: sender SENT, to SENT_TO, cc CC, bcc BCC
    assert gs._run_write.call_count == 4

    rel_types = []
    for call in gs._run_write.call_args_list:
        cypher = call[0][0]
        for rel in ["SENT", "SENT_TO", "CC", "BCC"]:
            if f":{rel}]" in cypher:
                rel_types.append(rel)
    assert sorted(rel_types) == ["BCC", "CC", "SENT", "SENT_TO"]


# ---------------------------------------------------------------------------
# Step 5: Email parsing utilities
# ---------------------------------------------------------------------------


def test_parse_email_address_display_and_angle():
    """Standard 'Display Name <addr>' format."""
    name, addr = parse_email_address("John Doe <john@example.com>")
    assert name == "John Doe"
    assert addr == "john@example.com"


def test_parse_email_address_bare():
    """Bare email address without display name."""
    name, addr = parse_email_address("john@example.com")
    assert name == ""
    assert addr == "john@example.com"


def test_parse_email_address_empty():
    """Empty string should return empty tuple."""
    name, addr = parse_email_address("")
    assert name == ""
    assert addr == ""


def test_parse_recipient_list():
    """Comma-separated recipient list."""
    results = parse_recipient_list("John Doe <john@example.com>, jane@example.com")
    assert len(results) == 2
    assert results[0] == ("John Doe", "john@example.com")
    assert results[1] == ("", "jane@example.com")


# ---------------------------------------------------------------------------
# Step 6: Temporal relationships
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_temporal_relationship(gs):
    """create_temporal_relationship should create edges with since/until props."""
    gs._run_write = AsyncMock()

    await gs.create_temporal_relationship(
        source_name="Alice",
        target_name="Bob",
        rel_type="REPORTS_TO",
        since="2023-01-01",
        until="2024-06-30",
        matter_id="m1",
    )

    gs._run_write.assert_called_once()
    cypher = gs._run_write.call_args[0][0]
    assert "REPORTS_TO" in cypher
    params = gs._run_write.call_args[0][1]
    assert params["since"] == "2023-01-01"
    assert params["until"] == "2024-06-30"


@pytest.mark.asyncio
async def test_create_temporal_relationship_invalid_type(gs):
    """Invalid relationship types should raise ValueError."""
    with pytest.raises(ValueError, match="Invalid temporal relationship type"):
        await gs.create_temporal_relationship(
            source_name="Alice",
            target_name="Bob",
            rel_type="FRIENDS_WITH",
        )


# ---------------------------------------------------------------------------
# Step 6: Communication pairs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_communication_pairs(gs):
    """get_communication_pairs should query bidirectional email traversal."""
    gs._run_query = AsyncMock(
        return_value=[
            {"email_id": "e1", "subject": "Re: Meeting", "date": "2024-01-15", "message_id": None},
        ]
    )

    results = await gs.get_communication_pairs(
        person_a="Alice",
        person_b="Bob",
        date_from="2024-01-01",
        date_to="2024-12-31",
        matter_id="m1",
    )

    assert len(results) == 1
    assert results[0]["email_id"] == "e1"

    # Verify Cypher uses correct relationship pattern
    cypher = gs._run_query.call_args[0][0]
    assert "SENT|SENT_TO|CC|BCC" in cypher


# ---------------------------------------------------------------------------
# Step 6: Reporting chain
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_reporting_chain(gs):
    """get_reporting_chain should traverse REPORTS_TO* edges."""
    gs._run_query = AsyncMock(
        return_value=[
            {"chain": ["Alice", "Bob", "CEO"], "depth": 2},
        ]
    )

    results = await gs.get_reporting_chain(person="Alice", matter_id="m1")

    assert len(results) == 1
    assert results[0]["chain"] == ["Alice", "Bob", "CEO"]

    cypher = gs._run_query.call_args[0][0]
    assert "REPORTS_TO*1..10" in cypher


# ---------------------------------------------------------------------------
# Step 6: Path finding
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_find_path(gs):
    """find_path should use shortestPath with configurable relationship types."""
    gs._run_query = AsyncMock(
        return_value=[
            {"nodes": ["Alice", "Acme", "Bob"], "relationships": ["MEMBER_OF", "MEMBER_OF"], "hops": 2},
        ]
    )

    results = await gs.find_path(
        entity_a="Alice",
        entity_b="Bob",
        max_hops=3,
        relationship_types=["MEMBER_OF", "REPORTS_TO"],
        matter_id="m1",
    )

    assert len(results) == 1
    assert results[0]["hops"] == 2

    cypher = gs._run_query.call_args[0][0]
    assert "shortestPath" in cypher
    assert "MEMBER_OF|REPORTS_TO" in cypher


# ---------------------------------------------------------------------------
# Step 7: Topics / DISCUSSES
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_topic_and_discusses(gs):
    """create_discusses_edge should create a Topic and link it."""
    gs._run_write = AsyncMock()

    await gs.create_discusses_edge(
        source_id="doc-1",
        source_label="Document",
        topic_name="Securities Fraud",
        matter_id="m1",
    )

    gs._run_write.assert_called_once()
    cypher = gs._run_write.call_args[0][0]
    assert "DISCUSSES" in cypher
    assert ":Topic" in cypher
    assert ":Document" in cypher


@pytest.mark.asyncio
async def test_create_discusses_invalid_source(gs):
    """source_label must be Email or Document."""
    with pytest.raises(ValueError, match="source_label must be"):
        await gs.create_discusses_edge(
            source_id="x",
            source_label="Chunk",
            topic_name="test",
        )


# ---------------------------------------------------------------------------
# Step 7: ALIAS_OF
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_alias_edge(gs):
    """create_alias_edge should create ALIAS_OF between term and canonical."""
    gs._run_write = AsyncMock()

    await gs.create_alias_edge(
        term="the Company",
        canonical_name="Acme Corporation",
        entity_type="organization",
        matter_id="m1",
    )

    gs._run_write.assert_called_once()
    cypher = gs._run_write.call_args[0][0]
    assert "ALIAS_OF" in cypher
    params = gs._run_write.call_args[0][1]
    assert params["term"] == "the Company"
    assert params["canonical_name"] == "Acme Corporation"


@pytest.mark.asyncio
async def test_create_alias_edge_idempotent(gs):
    """Calling create_alias_edge twice should use MERGE (idempotent)."""
    gs._run_write = AsyncMock()

    await gs.create_alias_edge("term", "canonical", "person")
    cypher = gs._run_write.call_args[0][0]
    assert "MERGE" in cypher


# ---------------------------------------------------------------------------
# Step 7: Batch entity lookup (Qdrant <-> Neo4j cross-ref)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_entities_by_names(gs):
    """get_entities_by_names should batch-fetch entities by name list."""
    gs._run_query = AsyncMock(
        return_value=[
            {"name": "Alice", "type": "person", "mention_count": 5, "labels": ["Entity", "Person"], "aliases": []},
            {"name": "Bob", "type": "person", "mention_count": 3, "labels": ["Entity", "Person"], "aliases": []},
        ]
    )

    results = await gs.get_entities_by_names(
        names=["Alice", "Bob", "Unknown"],
        matter_id="m1",
    )

    assert len(results) == 2

    cypher = gs._run_query.call_args[0][0]
    assert "e.name IN $names" in cypher
    assert "matter_id" in cypher


@pytest.mark.asyncio
async def test_get_entities_by_names_empty():
    """Empty names list should return empty results immediately."""
    driver = AsyncMock()
    gs = GraphService(driver)

    results = await gs.get_entities_by_names(names=[])
    assert results == []
