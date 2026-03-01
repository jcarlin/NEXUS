"""Tests for the communication_matrix LangGraph tool contract (M10c).

Covers:
- Tool invocation with InjectedState for matter_id extraction
- Entity name filtering and JSON output structure
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest

from app.analytics.schemas import (
    CommunicationMatrixResponse,
    CommunicationPair,
)

# ---------------------------------------------------------------------------
# Test 10: communication_matrix tool contract
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_communication_matrix_tool_contract():
    """Import the communication_matrix tool from app.query.tools.

    Mock the DB and service. Call the tool with a mock state dict containing
    _filters: {"matter_id": "test-matter"}. Verify matter_id extraction,
    entity_name filtering, and JSON output structure.
    """
    from app.query.tools import communication_matrix

    test_matter_id = "test-matter-001"
    mock_response = CommunicationMatrixResponse(
        matter_id=UUID("00000000-0000-0000-0000-000000000001"),
        pairs=[
            CommunicationPair(
                sender_name="Alice Smith",
                sender_email="alice@example.com",
                recipient_name="Bob Jones",
                recipient_email="bob@example.com",
                relationship_type="to",
                message_count=12,
            ),
        ],
        total_messages=12,
        unique_senders=1,
        unique_recipients=1,
    )

    # Mock the DB generator: get_db() returns an async generator.
    # The tool does: db_gen = get_db(); db = await db_gen.__anext__()
    mock_db = AsyncMock()

    async def _mock_get_db():
        yield mock_db

    with (
        patch(
            "app.dependencies.get_db",
            _mock_get_db,
        ),
        patch(
            "app.analytics.service.AnalyticsService.get_communication_matrix",
            new_callable=AsyncMock,
            return_value=mock_response,
        ) as mock_service,
    ):
        # Call the tool with entity_name and injected state
        state = {"_filters": {"matter_id": test_matter_id}}
        result = await communication_matrix.ainvoke(
            {"entity_name": "Alice Smith", "state": state},
        )

    # Verify the service was called with the correct matter_id from _filters
    mock_service.assert_called_once()
    call_args = mock_service.call_args
    # First positional arg is the db session, second is matter_id
    assert call_args[0][1] == test_matter_id

    # Verify entity_name was passed for filtering
    assert call_args[1].get("entity_name") == "Alice Smith"

    # Verify the output is valid JSON
    parsed = json.loads(result)

    # Verify the output structure matches the response schema
    assert "pairs" in parsed
    assert "total_messages" in parsed
    assert "unique_senders" in parsed
    assert "unique_recipients" in parsed
    assert parsed["total_messages"] == 12
    assert len(parsed["pairs"]) == 1
    assert parsed["pairs"][0]["sender_name"] == "Alice Smith"
    assert parsed["pairs"][0]["recipient_name"] == "Bob Jones"
    assert parsed["pairs"][0]["message_count"] == 12

    # --- Test without entity_name (None) ---
    with (
        patch(
            "app.dependencies.get_db",
            _mock_get_db,
        ),
        patch(
            "app.analytics.service.AnalyticsService.get_communication_matrix",
            new_callable=AsyncMock,
            return_value=mock_response,
        ),
    ):
        state = {"_filters": {"matter_id": test_matter_id}}
        result_no_filter = await communication_matrix.ainvoke(
            {"state": state},
        )

    # Should still work without entity_name
    parsed_2 = json.loads(result_no_filter)
    assert "pairs" in parsed_2
