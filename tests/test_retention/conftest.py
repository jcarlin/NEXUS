"""Shared fixtures for retention policy tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth.schemas import UserRecord

# ---------------------------------------------------------------------------
# Test constants
# ---------------------------------------------------------------------------

TEST_MATTER_ID = UUID("00000000-0000-0000-0000-000000000001")
TEST_USER_ID = UUID("00000000-0000-0000-0000-000000000099")
TEST_POLICY_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

ADMIN_USER = UserRecord(
    id=TEST_USER_ID,
    email="admin@nexus.dev",
    full_name="Admin User",
    role="admin",
    is_active=True,
    password_hash="$2b$12$fake",
    api_key_hash=None,
    created_at=datetime(2025, 1, 1, tzinfo=UTC),
    updated_at=datetime(2025, 1, 1, tzinfo=UTC),
)

REVIEWER_USER = UserRecord(
    id=UUID("00000000-0000-0000-0000-000000000088"),
    email="reviewer@nexus.dev",
    full_name="Reviewer User",
    role="reviewer",
    is_active=True,
    password_hash="$2b$12$fake",
    api_key_hash=None,
    created_at=datetime(2025, 1, 1, tzinfo=UTC),
    updated_at=datetime(2025, 1, 1, tzinfo=UTC),
)


def _make_policy_row(
    matter_id: UUID = TEST_MATTER_ID,
    status: str = "active",
    retention_days: int = 365,
    **overrides,
) -> dict:
    """Build a mock policy row dict."""
    row = {
        "id": overrides.get("id", TEST_POLICY_ID),
        "matter_id": matter_id,
        "retention_days": retention_days,
        "policy_set_by": TEST_USER_ID,
        "policy_set_at": datetime(2026, 1, 1, tzinfo=UTC),
        "purge_scheduled_at": datetime(2027, 1, 1, tzinfo=UTC),
        "purge_completed_at": None,
        "purge_error": None,
        "archive_path": None,
        "status": status,
    }
    row.update(overrides)
    return row


@pytest.fixture()
async def retention_client(_test_app) -> AsyncIterator[AsyncClient]:
    """Client with admin auth for retention tests."""
    from app.auth.middleware import get_current_user, get_matter_id

    saved = dict(_test_app.dependency_overrides)

    _test_app.dependency_overrides[get_current_user] = lambda: ADMIN_USER
    _test_app.dependency_overrides[get_matter_id] = lambda: TEST_MATTER_ID
    transport = ASGITransport(app=_test_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac

    _test_app.dependency_overrides = saved


@pytest.fixture()
async def reviewer_client(_test_app) -> AsyncIterator[AsyncClient]:
    """Client with reviewer role (non-admin)."""
    from app.auth.middleware import get_current_user, get_matter_id

    saved = dict(_test_app.dependency_overrides)

    _test_app.dependency_overrides[get_current_user] = lambda: REVIEWER_USER
    _test_app.dependency_overrides[get_matter_id] = lambda: TEST_MATTER_ID
    transport = ASGITransport(app=_test_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac

    _test_app.dependency_overrides = saved
