"""Tests for network centrality computation via Neo4j GDS (M10c).

Covers:
- Degree centrality computation and ranking
- PageRank and betweenness centrality (algorithm name verification)
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from app.entities.graph_service import GraphService

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
# Test 3: degree centrality computation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_centrality_degree_computation(gs):
    """Create a GraphService with mocked _run_query that returns GDS-like results.

    Mock _run_write for projection create/drop. Call compute_centrality()
    with metric="degree". Verify ranked list is returned correctly.
    """
    gds_results = [
        {"name": "Alice", "type": "person", "score": 5.0},
        {"name": "Bob", "type": "person", "score": 3.0},
        {"name": "Acme Corp", "type": "organization", "score": 2.0},
    ]

    gs._run_query = AsyncMock(return_value=gds_results)
    gs._run_write = AsyncMock()

    results = await gs.compute_centrality("matter-1", "degree")

    # Verify results are returned in score-descending order (from GDS)
    assert len(results) == 3
    assert results[0]["name"] == "Alice"
    assert results[0]["score"] == 5.0
    assert results[1]["name"] == "Bob"
    assert results[1]["score"] == 3.0
    assert results[2]["name"] == "Acme Corp"
    assert results[2]["score"] == 2.0

    # Verify projection was created (first _run_write call)
    assert gs._run_write.call_count >= 2  # project + drop
    project_cypher = gs._run_write.call_args_list[0][0][0]
    assert "gds.graph.project" in project_cypher

    # Verify the correct GDS algorithm was called
    stream_cypher = gs._run_query.call_args[0][0]
    assert "gds.degree.stream" in stream_cypher

    # Verify projection was dropped in finally block
    drop_cypher = gs._run_write.call_args_list[-1][0][0]
    assert "gds.graph.drop" in drop_cypher

    # Verify graph_name includes matter_id and metric
    project_params = gs._run_write.call_args_list[0][0][1]
    assert "matter-1" in project_params["graph_name"]
    assert "degree" in project_params["graph_name"]


# ---------------------------------------------------------------------------
# Test 4: pagerank and betweenness centrality
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_centrality_pagerank_betweenness(gs):
    """Test both pagerank and betweenness metrics.

    Verify sorted entities and correct GDS algorithm name in Cypher for each.
    """
    gds_results = [
        {"name": "Eve", "type": "person", "score": 0.85},
        {"name": "Frank", "type": "person", "score": 0.42},
    ]

    # --- Test PageRank ---
    gs._run_query = AsyncMock(return_value=gds_results)
    gs._run_write = AsyncMock()

    pagerank_results = await gs.compute_centrality("matter-1", "pagerank")

    assert len(pagerank_results) == 2
    assert pagerank_results[0]["name"] == "Eve"
    assert pagerank_results[0]["score"] == 0.85

    # Verify the correct GDS algorithm procedure was called
    pr_cypher = gs._run_query.call_args[0][0]
    assert "gds.pageRank.stream" in pr_cypher

    # Verify graph_name encodes the metric
    pr_project_params = gs._run_write.call_args_list[0][0][1]
    assert "pagerank" in pr_project_params["graph_name"]

    # --- Test Betweenness ---
    gs._run_query = AsyncMock(return_value=gds_results)
    gs._run_write = AsyncMock()

    betweenness_results = await gs.compute_centrality("matter-1", "betweenness")

    assert len(betweenness_results) == 2

    bw_cypher = gs._run_query.call_args[0][0]
    assert "gds.betweenness.stream" in bw_cypher

    bw_project_params = gs._run_write.call_args_list[0][0][1]
    assert "betweenness" in bw_project_params["graph_name"]

    # --- Test invalid metric ---
    with pytest.raises(ValueError, match="Invalid centrality metric"):
        await gs.compute_centrality("matter-1", "closeness")


# ---------------------------------------------------------------------------
# Test: network_analysis tool returns info when flag is disabled
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_network_analysis_tool_disabled_by_flag(monkeypatch):
    """When ENABLE_GRAPH_CENTRALITY is false, the tool returns an info message
    instead of calling Neo4j GDS."""
    monkeypatch.setenv("ENABLE_GRAPH_CENTRALITY", "false")

    from app.query.tools import network_analysis

    state = {"_filters": {"matter_id": "matter-1"}}
    result = await network_analysis.ainvoke(
        {"metric": "degree", "state": state},
    )

    parsed = json.loads(result)
    assert "info" in parsed
    assert "not enabled" in parsed["info"]


# ---------------------------------------------------------------------------
# Test: network centrality router returns 501 when flag is disabled
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_network_centrality_endpoint_disabled_by_flag(client, monkeypatch):
    """GET /analytics/network-centrality returns 501 when ENABLE_GRAPH_CENTRALITY
    is false."""
    monkeypatch.setenv("ENABLE_GRAPH_CENTRALITY", "false")

    resp = await client.get(
        "/api/v1/analytics/network-centrality",
        params={"metric": "degree"},
    )

    assert resp.status_code == 501
    assert "not enabled" in resp.json()["detail"]
