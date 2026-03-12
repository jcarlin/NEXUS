"""Tests for retention policy router endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from tests.test_retention.conftest import TEST_MATTER_ID, _make_policy_row

# ---------------------------------------------------------------------------
# POST /retention/policies
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_policy_success(client):
    """POST /retention/policies creates and returns policy."""
    row = _make_policy_row()

    with patch("app.retention.router.RetentionService") as mock_svc:
        mock_svc.get_policy = AsyncMock(return_value=None)
        mock_svc.create_policy = AsyncMock(return_value=row)

        response = await client.post(
            "/api/v1/retention/policies",
            json={"matter_id": str(TEST_MATTER_ID), "retention_days": 365},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["retention_days"] == 365
    assert data["status"] == "active"


@pytest.mark.asyncio
async def test_create_policy_non_admin_403(reviewer_client):
    """POST /retention/policies with non-admin role returns 403."""
    response = await reviewer_client.post(
        "/api/v1/retention/policies",
        json={"matter_id": str(TEST_MATTER_ID), "retention_days": 365},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_policy_duplicate_409(client):
    """POST /retention/policies with existing policy returns 409."""
    existing = _make_policy_row()

    with patch("app.retention.router.RetentionService") as mock_svc:
        mock_svc.get_policy = AsyncMock(return_value=existing)

        response = await client.post(
            "/api/v1/retention/policies",
            json={"matter_id": str(TEST_MATTER_ID), "retention_days": 365},
        )

    assert response.status_code == 409


# ---------------------------------------------------------------------------
# GET /retention/policies
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_policies(client):
    """GET /retention/policies returns list of policies."""
    rows = [_make_policy_row()]

    with patch("app.retention.router.RetentionService") as mock_svc:
        mock_svc.list_policies = AsyncMock(return_value=(rows, 1))

        response = await client.get("/api/v1/retention/policies")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert len(data["policies"]) == 1


# ---------------------------------------------------------------------------
# GET /retention/policies/{matter_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_policy_found(client):
    """GET /retention/policies/{matter_id} returns policy."""
    row = _make_policy_row()

    with patch("app.retention.router.RetentionService") as mock_svc:
        mock_svc.get_policy = AsyncMock(return_value=row)

        response = await client.get(f"/api/v1/retention/policies/{TEST_MATTER_ID}")

    assert response.status_code == 200
    assert response.json()["matter_id"] == str(TEST_MATTER_ID)


@pytest.mark.asyncio
async def test_get_policy_not_found_404(client):
    """GET /retention/policies/{matter_id} returns 404 when not found."""
    with patch("app.retention.router.RetentionService") as mock_svc:
        mock_svc.get_policy = AsyncMock(return_value=None)

        response = await client.get(f"/api/v1/retention/policies/{TEST_MATTER_ID}")

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /retention/policies/{matter_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_policy_succeeds(client):
    """DELETE /retention/policies/{matter_id} deletes active policy."""
    row = _make_policy_row(status="active")

    with patch("app.retention.router.RetentionService") as mock_svc:
        mock_svc.get_policy = AsyncMock(return_value=row)
        mock_svc.delete_policy = AsyncMock(return_value=True)

        response = await client.delete(f"/api/v1/retention/policies/{TEST_MATTER_ID}")

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_delete_policy_non_active_409(client):
    """DELETE /retention/policies/{matter_id} with non-active status returns 409."""
    row = _make_policy_row(status="purging")

    with patch("app.retention.router.RetentionService") as mock_svc:
        mock_svc.get_policy = AsyncMock(return_value=row)

        response = await client.delete(f"/api/v1/retention/policies/{TEST_MATTER_ID}")

    assert response.status_code == 409


# ---------------------------------------------------------------------------
# POST /retention/policies/{matter_id}/purge
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trigger_purge_success(client):
    """POST /retention/policies/{matter_id}/purge triggers purge."""
    row = _make_policy_row()

    with (
        patch("app.retention.router.RetentionService") as mock_svc,
        patch("app.retention.router.get_qdrant"),
        patch("app.retention.router.get_neo4j"),
        patch("app.retention.router.get_minio"),
    ):
        mock_svc.get_policy = AsyncMock(return_value=row)
        mock_svc.execute_purge = AsyncMock(return_value={"status": "completed", "archive_path": "archives/test.zip"})

        response = await client.post(f"/api/v1/retention/policies/{TEST_MATTER_ID}/purge")

    assert response.status_code == 200
    assert response.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_trigger_purge_non_admin_403(reviewer_client):
    """POST /retention/policies/{matter_id}/purge with non-admin returns 403."""
    response = await reviewer_client.post(f"/api/v1/retention/policies/{TEST_MATTER_ID}/purge")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_all_endpoints_require_admin(reviewer_client):
    """All retention endpoints return 403 for non-admin users."""
    endpoints = [
        ("POST", "/api/v1/retention/policies", {"matter_id": str(TEST_MATTER_ID), "retention_days": 365}),
        ("GET", "/api/v1/retention/policies", None),
        ("GET", f"/api/v1/retention/policies/{TEST_MATTER_ID}", None),
        ("DELETE", f"/api/v1/retention/policies/{TEST_MATTER_ID}", None),
        ("POST", f"/api/v1/retention/policies/{TEST_MATTER_ID}/purge", None),
    ]

    for method, url, body in endpoints:
        if method == "POST" and body:
            resp = await reviewer_client.post(url, json=body)
        elif method == "POST":
            resp = await reviewer_client.post(url)
        elif method == "GET":
            resp = await reviewer_client.get(url)
        elif method == "DELETE":
            resp = await reviewer_client.delete(url)
        assert resp.status_code == 403, f"{method} {url} returned {resp.status_code}, expected 403"


@pytest.mark.asyncio
async def test_purge_policy_not_found_404(client):
    """POST /policies/{matter_id}/purge returns 404 when no policy exists."""
    with patch("app.retention.router.RetentionService") as mock_svc:
        mock_svc.get_policy = AsyncMock(return_value=None)

        response = await client.post(f"/api/v1/retention/policies/{TEST_MATTER_ID}/purge")

    assert response.status_code == 404
