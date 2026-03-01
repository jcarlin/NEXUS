"""Tests for analytics API router endpoints (M10c).

Covers:
- GET /analytics/communication-matrix endpoint
- GET /analytics/network-centrality endpoint
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest

from app.analytics.schemas import (
    CentralityMetric,
    CommunicationMatrixResponse,
    CommunicationPair,
    EntityCentrality,
    NetworkCentralityResponse,
)

# ---------------------------------------------------------------------------
# Test 8: communication matrix endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_communication_matrix_endpoint(client):
    """Use the client fixture. Patch AnalyticsService.get_communication_matrix.

    GET /api/v1/analytics/communication-matrix. Verify 200 + response schema.
    Verify matter_id was passed from the test fixture.
    """
    test_matter_id = UUID("00000000-0000-0000-0000-000000000001")

    mock_response = CommunicationMatrixResponse(
        matter_id=test_matter_id,
        pairs=[
            CommunicationPair(
                sender_name="Alice Smith",
                sender_email="alice@example.com",
                recipient_name="Bob Jones",
                recipient_email="bob@example.com",
                relationship_type="to",
                message_count=15,
            ),
            CommunicationPair(
                sender_name="Bob Jones",
                sender_email="bob@example.com",
                recipient_name="Alice Smith",
                recipient_email="alice@example.com",
                relationship_type="to",
                message_count=10,
            ),
        ],
        total_messages=25,
        unique_senders=2,
        unique_recipients=2,
    )

    with patch(
        "app.analytics.router.AnalyticsService.get_communication_matrix",
        new_callable=AsyncMock,
        return_value=mock_response,
    ) as mock_service:
        resp = await client.get("/api/v1/analytics/communication-matrix")

    assert resp.status_code == 200
    body = resp.json()

    # Verify response schema structure
    assert body["matter_id"] == str(test_matter_id)
    assert len(body["pairs"]) == 2
    assert body["total_messages"] == 25
    assert body["unique_senders"] == 2
    assert body["unique_recipients"] == 2

    # Verify pair data
    assert body["pairs"][0]["sender_name"] == "Alice Smith"
    assert body["pairs"][0]["message_count"] == 15

    # Verify matter_id was passed correctly from the fixture
    mock_service.assert_called_once()
    call_args = mock_service.call_args
    # Second positional arg is matter_id string
    assert call_args[0][1] == str(test_matter_id)


# ---------------------------------------------------------------------------
# Test 9: network centrality endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_network_centrality_endpoint(client):
    """Use the client fixture. Patch AnalyticsService.get_network_centrality.

    GET /api/v1/analytics/network-centrality?metric=degree. Verify 200 + schema.
    Test invalid metric -> 422.
    """
    test_matter_id = UUID("00000000-0000-0000-0000-000000000001")

    mock_response = NetworkCentralityResponse(
        matter_id=test_matter_id,
        metric=CentralityMetric.DEGREE,
        entities=[
            EntityCentrality(name="Alice", entity_type="person", score=5.0, rank=1),
            EntityCentrality(name="Bob", entity_type="person", score=3.0, rank=2),
            EntityCentrality(name="Acme Corp", entity_type="organization", score=2.0, rank=3),
        ],
        total_entities=3,
    )

    with patch(
        "app.analytics.router.AnalyticsService.get_network_centrality",
        new_callable=AsyncMock,
        return_value=mock_response,
    ) as mock_service:
        resp = await client.get(
            "/api/v1/analytics/network-centrality",
            params={"metric": "degree"},
        )

    assert resp.status_code == 200
    body = resp.json()

    # Verify response schema
    assert body["matter_id"] == str(test_matter_id)
    assert body["metric"] == "degree"
    assert len(body["entities"]) == 3
    assert body["total_entities"] == 3

    # Verify entity data and ranking
    assert body["entities"][0]["name"] == "Alice"
    assert body["entities"][0]["score"] == 5.0
    assert body["entities"][0]["rank"] == 1
    assert body["entities"][2]["name"] == "Acme Corp"
    assert body["entities"][2]["rank"] == 3

    # Verify service was called with correct params
    mock_service.assert_called_once()
    call_args = mock_service.call_args
    assert call_args[0][1] == str(test_matter_id)
    assert call_args[0][2] == "degree"

    # --- Test invalid metric returns 422 ---
    resp_invalid = await client.get(
        "/api/v1/analytics/network-centrality",
        params={"metric": "closeness"},
    )
    assert resp_invalid.status_code == 422
