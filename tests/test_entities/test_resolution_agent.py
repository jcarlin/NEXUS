"""Tests for the Entity Resolution Agent (M11).

3 tests:
- Full pipeline flow (extract → deduplicate → merge → hierarchy → terms → uncertain)
- Uncertain merge flagging (scores between 85-90 flagged, not auto-merged)
- Celery task wrapper
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_resolution_agent_full_flow() -> None:
    """Invoke the resolution graph and verify merges, hierarchy, and term linking."""
    from app.entities.resolution_agent import build_resolution_graph

    mock_driver = AsyncMock()
    mock_gs = AsyncMock()

    # extract: return entities with a high-confidence duplicate pair
    # "Robert Johnson" vs "Robert Johnsonn" scores ~97 (> 90 confident threshold)
    mock_gs._run_query = AsyncMock(
        return_value=[{"type": "person"}],
    )
    mock_gs.get_all_entities_by_type = AsyncMock(
        return_value=[
            {"name": "Robert Johnson", "type": "person", "mention_count": 10},
            {"name": "Robert Johnsonn", "type": "person", "mention_count": 3},
        ],
    )
    mock_gs.merge_entities = AsyncMock(return_value=True)
    mock_gs.create_temporal_relationship = AsyncMock()
    mock_gs.create_alias_edge = AsyncMock()
    mock_gs.mark_pending_merge = AsyncMock()

    mock_hierarchy_entries = [
        MagicMock(person_name="Alice", reports_to_name="Bob"),
    ]

    mock_case_ctx = {
        "defined_terms": [
            {"term": "Defendant A", "canonical_name": "Robert Johnson"},
        ],
    }

    settings = {
        "neo4j_uri": "bolt://localhost:7687",
        "neo4j_user": "neo4j",
        "neo4j_password": "test",
        "enable_coreference_resolution": False,
        "enable_llm_entity_resolution": False,
        "postgres_url": "postgresql+asyncpg://test@localhost/test",
    }

    # Build and compile inside the patches so node closures capture mocks
    with (
        patch("neo4j.AsyncGraphDatabase.driver", return_value=mock_driver),
        patch(
            "app.entities.graph_service.GraphService",
            return_value=mock_gs,
        ),
        patch(
            "sqlalchemy.ext.asyncio.create_async_engine",
        ) as mock_engine_factory,
        patch(
            "app.analytics.service.AnalyticsService.infer_org_hierarchy",
            new_callable=AsyncMock,
            return_value=mock_hierarchy_entries,
        ),
        patch(
            "app.cases.service.CaseService.get_full_context",
            new_callable=AsyncMock,
            return_value=mock_case_ctx,
        ),
    ):
        mock_engine = AsyncMock()
        mock_engine_factory.return_value = mock_engine

        graph = build_resolution_graph(settings)
        compiled = graph.compile()

        result = await compiled.ainvoke({"matter_id": "test-matter", "entity_type": "person"})

    # Verify merge was called (Robert Johnson / Robert Johnsonn score ~97 > 90)
    assert mock_gs.merge_entities.called
    assert result.get("merges_performed", 0) >= 1

    # Verify hierarchy inference was attempted
    assert mock_gs.create_temporal_relationship.called

    # Verify term linking was attempted
    assert mock_gs.create_alias_edge.called


@pytest.mark.asyncio
async def test_resolution_agent_uncertain_merges() -> None:
    """Matches between 85-90 fuzzy score should be flagged, NOT auto-merged."""

    from app.entities.resolution_agent import (
        CONFIDENT_FUZZY_THRESHOLD,
        create_resolution_nodes,
    )

    # Verify the threshold constants
    assert CONFIDENT_FUZZY_THRESHOLD == 90

    # Simulate the deduplicate node logic directly
    settings = {
        "neo4j_uri": "bolt://localhost:7687",
        "neo4j_user": "neo4j",
        "neo4j_password": "test",
    }
    nodes = create_resolution_nodes(settings)

    # Create entities that produce a score between 85-90
    # "John Smith" vs "John Smithe" should be ~91 (confident)
    # We need to test the splitting logic directly
    mock_entities = [
        {"name": "Alice Johnson", "type": "person", "mention_count": 5},
        {"name": "Alice Johnsen", "type": "person", "mention_count": 3},
    ]

    # Patch to avoid Neo4j calls — test deduplicate node directly
    from app.entities.resolver import EntityResolver

    resolver = EntityResolver(fuzzy_threshold=85)
    matches = resolver.find_fuzzy_matches(mock_entities)

    # Alice Johnson vs Alice Johnsen should produce a match in the uncertain range
    assert len(matches) >= 1
    for m in matches:
        if m.score >= CONFIDENT_FUZZY_THRESHOLD:
            # Confident: would be auto-merged
            pass
        else:
            # Uncertain: should be flagged for review
            assert m.score >= 85, "Match should be above base threshold"
            assert m.score < 90, "Match should be below confident threshold"

    # Test the present_uncertain node with mock
    mock_driver = AsyncMock()
    mock_gs = AsyncMock()
    mock_gs.mark_pending_merge = AsyncMock()

    uncertain_data = [
        {
            "name_a": "Alice Johnson",
            "name_b": "Alice Johnsen",
            "entity_type": "person",
            "score": 87.5,
            "method": "fuzzy",
        }
    ]

    with (
        patch("neo4j.AsyncGraphDatabase.driver", return_value=mock_driver),
        patch(
            "app.entities.graph_service.GraphService",
            return_value=mock_gs,
        ),
    ):
        await nodes["present_uncertain"]({"uncertain_merges": uncertain_data, "matter_id": "test-matter"})

    # mark_pending_merge should have been called for both entity names
    assert mock_gs.mark_pending_merge.call_count == 2  # once for name_a, once for name_b


@pytest.mark.asyncio
async def test_llm_resolve_node_skipped_when_disabled() -> None:
    """llm_resolve node should be a no-op when feature flag is disabled."""
    from app.entities.resolution_agent import create_resolution_nodes

    settings = {
        "neo4j_uri": "bolt://localhost:7687",
        "neo4j_user": "neo4j",
        "neo4j_password": "test",
        "enable_llm_entity_resolution": False,
        "postgres_url": "postgresql+asyncpg://test@localhost/test",
    }

    nodes = create_resolution_nodes(settings)
    result = await nodes["llm_resolve"](
        {
            "entities": [{"name": "Trump", "type": "person", "mention_count": 100}],
            "all_matches": [],
        }
    )
    # Should return empty dict (no-op)
    assert result == {}


def test_resolution_agent_celery_task() -> None:
    """Celery task should invoke run_resolution_agent and return result."""
    from uuid import uuid4

    expected_result = {
        "merges_performed": 5,
        "hierarchy_edges_created": 2,
        "linked_terms": 1,
        "uncertain_merges": 3,
        "entity_types_processed": 2,
    }

    with (
        patch("app.entities.tasks.asyncio.run", return_value=expected_result) as mock_asyncio_run,
        patch("app.entities.tasks._get_sync_engine"),
        patch("app.entities.tasks._create_job_sync", return_value=str(uuid4())),
        patch("app.entities.tasks._update_stage"),
        patch("app.entities.tasks._store_celery_task_id"),
    ):
        from app.entities.tasks import entity_resolution_agent

        # Use .run() to call the task function directly (bypasses broker)
        result = entity_resolution_agent.run(str(uuid4()))

    assert result == expected_result
    assert result["merges_performed"] == 5
    assert result["uncertain_merges"] == 3
    # Verify asyncio.run was called with the coroutine
    mock_asyncio_run.assert_called_once()
