"""Tests for communication pair computation and matrix aggregation (M10c).

Covers:
- Extracting sender/recipient pairs from email document metadata JSONB
- Aggregating pre-computed communication_pairs into a matrix response
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from app.analytics.service import AnalyticsService

# ---------------------------------------------------------------------------
# Test 1: compute_communication_pairs from email metadata
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compute_communication_pairs_from_email_metadata():
    """Mock an AsyncSession with email documents containing metadata_ JSONB.

    Call AnalyticsService.compute_communication_pairs() and verify the correct
    UPSERT SQL is executed with the right params for each sender-recipient pair.
    """
    # Simulate two email documents with metadata_ JSONB
    doc_rows = [
        SimpleNamespace(
            id="doc-1",
            metadata_={
                "from_name": "Alice Smith",
                "from_email": "alice@example.com",
                "to": "Bob Jones <bob@example.com>, charlie@example.com",
                "cc": "Diana <diana@example.com>",
                "date": "2024-03-15",
            },
        ),
        SimpleNamespace(
            id="doc-2",
            metadata_={
                "from_name": "Bob Jones",
                "from_email": "bob@example.com",
                "to": "alice@example.com",
                "date": "2024-03-16",
            },
        ),
    ]

    mock_db = AsyncMock()
    # First call returns email docs; subsequent calls are UPSERT executions.
    # The result of `await db.execute()` has a synchronous `.fetchall()`,
    # so we use MagicMock (not AsyncMock) for the result object.
    fetch_result = MagicMock()
    fetch_result.fetchall.return_value = doc_rows
    mock_db.execute = AsyncMock(return_value=fetch_result)

    count = await AnalyticsService.compute_communication_pairs(
        mock_db,
        "matter-1",
    )

    # doc-1 produces: alice->bob (to), alice->charlie (to), alice->diana (cc) = 3
    # doc-2 produces: bob->alice (to) = 1
    # Total = 4 upserts
    assert count == 4

    # First call is the SELECT for email docs; remaining are UPSERTs
    all_calls = mock_db.execute.call_args_list
    # 1 SELECT + 4 UPSERTs = 5 total execute calls
    assert len(all_calls) == 5

    # Verify the SELECT query was for email documents
    select_query_str = str(all_calls[0][0][0])
    assert "documents" in select_query_str
    assert "matter_id" in select_query_str

    # Verify UPSERT params for the first recipient (bob)
    upsert_params = all_calls[1][0][1]
    assert upsert_params["matter_id"] == "matter-1"
    assert upsert_params["sender_email"] == "alice@example.com"
    assert upsert_params["recipient_email"] == "bob@example.com"
    assert upsert_params["rel_type"] == "to"
    assert upsert_params["email_date"] == "2024-03-15"

    # Verify the cc recipient (diana) was processed
    upsert_4_params = all_calls[3][0][1]
    assert upsert_4_params["recipient_email"] == "diana@example.com"
    assert upsert_4_params["rel_type"] == "cc"
    assert upsert_4_params["sender_name"] == "Alice Smith"


# ---------------------------------------------------------------------------
# Test 2: communication matrix aggregation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_communication_matrix_aggregation():
    """Mock db.execute to return pre-populated communication_pairs rows.

    Call get_communication_matrix() and verify the response has correct NxN
    structure, totals, and entity filtering works.
    """
    # Simulate pre-computed communication_pairs rows
    matrix_rows = [
        SimpleNamespace(
            sender_name="Alice Smith",
            sender_email="alice@example.com",
            recipient_name="Bob Jones",
            recipient_email="bob@example.com",
            relationship_type="to",
            message_count=15,
            earliest=datetime(2024, 1, 1),
            latest=datetime(2024, 6, 30),
        ),
        SimpleNamespace(
            sender_name="Alice Smith",
            sender_email="alice@example.com",
            recipient_name="Charlie Davis",
            recipient_email="charlie@example.com",
            relationship_type="cc",
            message_count=5,
            earliest=datetime(2024, 2, 1),
            latest=datetime(2024, 5, 15),
        ),
        SimpleNamespace(
            sender_name="Bob Jones",
            sender_email="bob@example.com",
            recipient_name="Alice Smith",
            recipient_email="alice@example.com",
            relationship_type="to",
            message_count=10,
            earliest=datetime(2024, 1, 15),
            latest=datetime(2024, 6, 25),
        ),
    ]

    mock_db = AsyncMock()
    # The result of `await db.execute()` has a synchronous `.fetchall()`,
    # so we use MagicMock (not AsyncMock) for the result object.
    fetch_result = MagicMock()
    fetch_result.fetchall.return_value = matrix_rows
    mock_db.execute = AsyncMock(return_value=fetch_result)

    matter_id = "00000000-0000-0000-0000-000000000001"
    response = await AnalyticsService.get_communication_matrix(
        mock_db,
        matter_id,
    )

    # Verify response structure
    assert response.matter_id == UUID(matter_id)
    assert len(response.pairs) == 3
    assert response.total_messages == 30  # 15 + 5 + 10
    assert response.unique_senders == 2  # alice, bob
    assert response.unique_recipients == 3  # bob, charlie, alice

    # Verify pairs are ordered by message_count (from the SQL ORDER BY)
    assert response.pairs[0].message_count == 15
    assert response.pairs[0].sender_name == "Alice Smith"
    assert response.pairs[0].recipient_name == "Bob Jones"

    # Now test entity_name filtering — verify the SQL includes the filter
    mock_db.execute.reset_mock()
    fetch_result_filtered = MagicMock()
    fetch_result_filtered.fetchall.return_value = [matrix_rows[0], matrix_rows[2]]
    mock_db.execute = AsyncMock(return_value=fetch_result_filtered)

    filtered = await AnalyticsService.get_communication_matrix(
        mock_db,
        matter_id,
        entity_name="Alice Smith",
    )

    # Verify entity_name filter was passed in SQL params
    sql_params = mock_db.execute.call_args[0][1]
    assert sql_params["entity_name"] == "Alice Smith"
    assert sql_params["matter_id"] == matter_id

    # Verify filtered results
    assert len(filtered.pairs) == 2
    assert filtered.total_messages == 25  # 15 + 10
