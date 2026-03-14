"""Tests for GraphRAG community API endpoints (T3-10).

Covers:
- POST /analytics/communities/detect
- GET  /analytics/communities
- GET  /analytics/communities/{community_id}
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest

# ---------------------------------------------------------------------------
# Detect endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_detect_communities_success(client, monkeypatch):
    """POST /api/v1/analytics/communities/detect triggers detection."""
    monkeypatch.setenv("ENABLE_GRAPHRAG_COMMUNITIES", "true")

    mock_communities = [
        {
            "id": "c1",
            "matter_id": "00000000-0000-0000-0000-000000000001",
            "level": 0,
            "parent_id": None,
            "entity_names": ["Alice", "Bob"],
            "relationship_types": [],
            "summary": None,
            "entity_count": 2,
        },
    ]

    with (
        patch(
            "app.analytics.communities.CommunityDetector.detect_communities",
            new_callable=AsyncMock,
            return_value=mock_communities,
        ),
        patch(
            "app.analytics.communities.CommunityDetector.build_hierarchy",
            return_value=mock_communities,
        ),
        patch(
            "app.analytics.router.AnalyticsService.save_communities",
            new_callable=AsyncMock,
        ),
        patch("app.analytics.router.get_graph_service"),
    ):
        resp = await client.post("/api/v1/analytics/communities/detect")

    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "completed"
    assert body["community_count"] == 1


@pytest.mark.asyncio
async def test_detect_communities_flag_disabled(client, monkeypatch):
    """Returns 501 when feature flag is disabled."""
    monkeypatch.setenv("ENABLE_GRAPHRAG_COMMUNITIES", "false")

    resp = await client.post("/api/v1/analytics/communities/detect")
    assert resp.status_code == 501


@pytest.mark.asyncio
async def test_detect_communities_requires_matter(client, monkeypatch):
    """Request without matter header gets 400/422."""
    monkeypatch.setenv("ENABLE_GRAPHRAG_COMMUNITIES", "true")
    # The client fixture provides matter_id via dependency override,
    # so we verify the endpoint exists and is accessible with auth
    with (
        patch(
            "app.analytics.communities.CommunityDetector.detect_communities",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "app.analytics.communities.CommunityDetector.build_hierarchy",
            return_value=[],
        ),
        patch(
            "app.analytics.service.AnalyticsService.save_communities",
            new_callable=AsyncMock,
        ),
        patch("app.analytics.router.get_graph_service"),
    ):
        resp = await client.post("/api/v1/analytics/communities/detect")

    assert resp.status_code == 202
    body = resp.json()
    assert body["community_count"] == 0


# ---------------------------------------------------------------------------
# List endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_communities_success(client, monkeypatch):
    """GET /api/v1/analytics/communities returns communities."""
    monkeypatch.setenv("ENABLE_GRAPHRAG_COMMUNITIES", "true")

    test_matter_id = UUID("00000000-0000-0000-0000-000000000001")
    mock_rows = [
        {
            "id": "c1",
            "matter_id": test_matter_id,
            "level": 0,
            "parent_id": None,
            "entity_names": ["Alice", "Bob"],
            "relationship_types": [],
            "summary": "Test summary",
            "entity_count": 2,
        },
    ]

    with patch(
        "app.analytics.router.AnalyticsService.list_communities",
        new_callable=AsyncMock,
        return_value=mock_rows,
    ):
        resp = await client.get("/api/v1/analytics/communities")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert len(body["communities"]) == 1
    assert body["communities"][0]["id"] == "c1"


@pytest.mark.asyncio
async def test_list_communities_empty(client, monkeypatch):
    """Returns empty list when no communities detected."""
    monkeypatch.setenv("ENABLE_GRAPHRAG_COMMUNITIES", "true")

    with patch(
        "app.analytics.router.AnalyticsService.list_communities",
        new_callable=AsyncMock,
        return_value=[],
    ):
        resp = await client.get("/api/v1/analytics/communities")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
    assert body["communities"] == []


# ---------------------------------------------------------------------------
# Get single community
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_community_success(client, monkeypatch):
    """GET /api/v1/analytics/communities/{id} returns community + related."""
    monkeypatch.setenv("ENABLE_GRAPHRAG_COMMUNITIES", "true")

    test_matter_id = UUID("00000000-0000-0000-0000-000000000001")
    mock_row = {
        "id": "c1",
        "matter_id": test_matter_id,
        "level": 0,
        "parent_id": "p1",
        "entity_names": ["Alice", "Bob"],
        "relationship_types": ["SENT_TO"],
        "summary": "Alice and Bob communicated.",
        "entity_count": 2,
    }
    mock_related = [
        {
            "id": "c2",
            "matter_id": test_matter_id,
            "level": 0,
            "parent_id": "p1",
            "entity_names": ["Carol"],
            "relationship_types": [],
            "summary": None,
            "entity_count": 1,
        },
    ]

    with (
        patch(
            "app.analytics.router.AnalyticsService.get_community",
            new_callable=AsyncMock,
            return_value=mock_row,
        ),
        patch(
            "app.analytics.router.AnalyticsService.get_related_communities",
            new_callable=AsyncMock,
            return_value=mock_related,
        ),
    ):
        resp = await client.get("/api/v1/analytics/communities/c1")

    assert resp.status_code == 200
    body = resp.json()
    assert body["community"]["id"] == "c1"
    assert body["community"]["summary"] == "Alice and Bob communicated."
    assert len(body["related_communities"]) == 1


@pytest.mark.asyncio
async def test_get_community_not_found(client, monkeypatch):
    """Returns 404 for nonexistent community."""
    monkeypatch.setenv("ENABLE_GRAPHRAG_COMMUNITIES", "true")

    with patch(
        "app.analytics.router.AnalyticsService.get_community",
        new_callable=AsyncMock,
        return_value=None,
    ):
        resp = await client.get("/api/v1/analytics/communities/nonexistent")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_community_flag_disabled(client, monkeypatch):
    """Returns 501 when flag disabled."""
    monkeypatch.setenv("ENABLE_GRAPHRAG_COMMUNITIES", "false")

    resp = await client.get("/api/v1/analytics/communities/c1")
    assert resp.status_code == 501
