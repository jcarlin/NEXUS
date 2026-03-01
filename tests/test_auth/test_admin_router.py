"""Tests for admin-only API endpoints (audit log)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient

from app.auth.schemas import UserRecord

# ---------------------------------------------------------------------------
# GET /admin/audit-log
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_log_admin_200(client: AsyncClient) -> None:
    """Admin can access the audit log endpoint with paginated response."""
    fake_rows = [
        {
            "id": uuid4(),
            "user_id": UUID("00000000-0000-0000-0000-000000000099"),
            "user_email": "test@nexus.dev",
            "action": "GET",
            "resource": "/api/v1/documents",
            "resource_type": "documents",
            "matter_id": UUID("00000000-0000-0000-0000-000000000001"),
            "ip_address": "127.0.0.1",
            "user_agent": "testclient",
            "status_code": 200,
            "duration_ms": 12.5,
            "request_id": "test-req-id",
            "created_at": datetime.now(UTC),
        }
    ]

    # Mock the two DB calls: count query and data query
    # Use MagicMock (not AsyncMock) because scalar_one() and mappings().all()
    # are synchronous methods on the SQLAlchemy Result object.
    mock_count_result = MagicMock()
    mock_count_result.scalar_one.return_value = 1

    mock_data_result = MagicMock()
    mock_data_result.mappings.return_value.all.return_value = fake_rows

    call_count = 0

    async def mock_execute(query, params=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return mock_count_result
        return mock_data_result

    with patch("app.dependencies.get_session_factory") as mock_factory:
        mock_session = AsyncMock()
        mock_session.execute = mock_execute
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value = lambda: mock_session

        # Override get_db to use our mock session
        from app.dependencies import get_db

        async def mock_get_db():
            yield mock_session

        client._transport.app.dependency_overrides[get_db] = mock_get_db

        try:
            response = await client.get("/api/v1/admin/audit-log")
        finally:
            del client._transport.app.dependency_overrides[get_db]

    assert response.status_code == 200
    body = response.json()
    assert "items" in body
    assert "total" in body
    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["action"] == "GET"


@pytest.mark.asyncio
async def test_audit_log_non_admin_403(client: AsyncClient) -> None:
    """Non-admin users get 403 on the audit log endpoint."""
    from app.auth.middleware import get_current_user

    reviewer_user = UserRecord(
        id=UUID("00000000-0000-0000-0000-000000000077"),
        email="reviewer@nexus.dev",
        full_name="Doc Reviewer",
        role="reviewer",
        is_active=True,
        created_at=datetime.now(UTC),
    )

    client._transport.app.dependency_overrides[get_current_user] = lambda: reviewer_user

    try:
        response = await client.get("/api/v1/admin/audit-log")
    finally:
        from tests.conftest import _TEST_USER

        client._transport.app.dependency_overrides[get_current_user] = lambda: _TEST_USER

    assert response.status_code == 403
