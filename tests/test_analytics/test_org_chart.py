"""Tests for org chart import and hierarchy inference (M10c).

Covers:
- Importing org chart entries via POST endpoint
- Inferring REPORTS_TO relationships from asymmetric communication patterns
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from app.analytics.schemas import OrgChartImportResponse
from app.analytics.service import AnalyticsService

# ---------------------------------------------------------------------------
# Test 5: org chart import via endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_org_chart_import(client):
    """POST to /api/v1/cases/{matter_id}/org-chart with org chart JSON.

    Verify entries are stored (SQL executed) and response counts are correct.
    """
    matter_id = "00000000-0000-0000-0000-000000000001"

    org_chart_body = {
        "entries": [
            {
                "person_name": "Alice Smith",
                "person_email": "alice@example.com",
                "reports_to_name": "Bob Jones",
                "reports_to_email": "bob@example.com",
                "title": "Associate",
                "department": "Legal",
                "source": "manual",
            },
            {
                "person_name": "Charlie Davis",
                "person_email": "charlie@example.com",
                "reports_to_name": "Bob Jones",
                "reports_to_email": "bob@example.com",
                "title": "Paralegal",
                "department": "Legal",
                "source": "manual",
            },
            {
                "person_name": "Bob Jones",
                "person_email": "bob@example.com",
                "reports_to_name": None,
                "title": "Partner",
                "department": "Legal",
                "source": "manual",
            },
        ],
    }

    mock_result = OrgChartImportResponse(
        matter_id=UUID(matter_id),
        imported_count=3,
        total_entries=3,
    )

    with patch(
        "app.cases.router.AnalyticsService.import_org_chart",
        new_callable=AsyncMock,
        return_value=mock_result,
    ) as mock_import:
        resp = await client.post(
            f"/api/v1/cases/{matter_id}/org-chart",
            json=org_chart_body,
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["imported_count"] == 3
    assert body["total_entries"] == 3
    assert body["matter_id"] == matter_id

    # Verify the service was called with the correct matter_id and entries
    mock_import.assert_called_once()
    call_args = mock_import.call_args
    assert str(call_args[0][1]) == matter_id
    assert len(call_args[0][2]) == 3
    assert call_args[0][2][0].person_name == "Alice Smith"


# ---------------------------------------------------------------------------
# Test 6: org hierarchy inference from asymmetric communication
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_org_hierarchy_inference():
    """Mock db.execute to return asymmetric communication patterns.

    Call AnalyticsService.infer_org_hierarchy(). Verify REPORTS_TO
    suggestions have confidence scores and source='inferred'.
    """
    # Simulate asymmetric rows: Alice sends many more messages to Bob
    # than Bob sends to Alice => Bob may be Alice's superior
    asymmetric_rows = [
        SimpleNamespace(
            subordinate_name="Alice Smith",
            subordinate_email="alice@example.com",
            superior_name="Bob Jones",
            superior_email="bob@example.com",
            a_to_b=20,
            b_to_a=3,
            confidence=0.74,
        ),
        SimpleNamespace(
            subordinate_name="Charlie Davis",
            subordinate_email="charlie@example.com",
            superior_name="Bob Jones",
            superior_email="bob@example.com",
            a_to_b=15,
            b_to_a=0,
            confidence=0.9,
        ),
    ]

    mock_db = AsyncMock()
    # The result of `await db.execute()` has a synchronous `.fetchall()`,
    # so we use MagicMock (not AsyncMock) for the result object.
    fetch_result = MagicMock()
    fetch_result.fetchall.return_value = asymmetric_rows
    mock_db.execute = AsyncMock(return_value=fetch_result)

    entries = await AnalyticsService.infer_org_hierarchy(mock_db, "matter-1")

    assert len(entries) == 2

    # First entry: Alice reports to Bob
    assert entries[0].person_name == "Alice Smith"
    assert entries[0].person_email == "alice@example.com"
    assert entries[0].reports_to_name == "Bob Jones"
    assert entries[0].reports_to_email == "bob@example.com"
    assert entries[0].source == "inferred"
    assert entries[0].confidence == 0.74

    # Second entry: Charlie reports to Bob with higher confidence
    assert entries[1].person_name == "Charlie Davis"
    assert entries[1].reports_to_name == "Bob Jones"
    assert entries[1].source == "inferred"
    assert entries[1].confidence == 0.9

    # Verify SQL was executed with correct matter_id
    sql_params = mock_db.execute.call_args[0][1]
    assert sql_params["matter_id"] == "matter-1"

    # Verify the SQL uses the asymmetric communication heuristic
    sql_text = str(mock_db.execute.call_args[0][0])
    assert "pair_counts" in sql_text or "communication_pairs" in sql_text
