"""Tests for M11 router endpoints (communication-pairs, reporting-chain, path)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_communication_pairs_endpoint(client: AsyncClient) -> None:
    """GET /graph/communication-pairs should return emails between two people."""
    mock_gs = AsyncMock()
    mock_gs.get_communication_pairs = AsyncMock(
        return_value=[
            {
                "email_id": "em-001",
                "subject": "Meeting tomorrow",
                "date": "2024-03-15",
                "message_id": "<abc@example.com>",
            },
            {
                "email_id": "em-002",
                "subject": "Re: Meeting tomorrow",
                "date": "2024-03-16",
                "message_id": "<def@example.com>",
            },
        ]
    )

    with patch("app.dependencies._graph_service", mock_gs):
        response = await client.get(
            "/api/v1/graph/communication-pairs",
            params={"person_a": "Alice", "person_b": "Bob"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["person_a"] == "Alice"
    assert body["person_b"] == "Bob"
    assert body["total"] == 2
    assert len(body["emails"]) == 2
    assert body["emails"][0]["email_id"] == "em-001"
    assert body["emails"][1]["subject"] == "Re: Meeting tomorrow"


@pytest.mark.asyncio
async def test_reporting_chain_endpoint(client: AsyncClient) -> None:
    """GET /graph/reporting-chain/{person} should return chain data."""
    mock_gs = AsyncMock()
    mock_gs.get_reporting_chain = AsyncMock(
        return_value=[
            {"chain": ["Alice", "Bob", "Carol"], "depth": 2},
        ]
    )

    with patch("app.dependencies._graph_service", mock_gs):
        response = await client.get("/api/v1/graph/reporting-chain/Alice")

    assert response.status_code == 200
    body = response.json()
    assert body["person"] == "Alice"
    assert len(body["chains"]) == 1
    assert body["chains"][0]["chain"] == ["Alice", "Bob", "Carol"]
    assert body["chains"][0]["depth"] == 2
