"""E2E tests for GET /api/v1/health.

No auth required. Verifies that the health endpoint returns the correct
structure and reports all 5 services as healthy when Docker services are up.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

HEALTH_URL = "/api/v1/health"
EXPECTED_SERVICES = {"qdrant", "minio", "neo4j", "redis", "postgres"}


@pytest.mark.e2e
async def test_health_all_services_ok(e2e_client: AsyncClient) -> None:
    """Health endpoint returns 200 with status 'healthy' and all services 'ok'."""
    resp = await e2e_client.get(HEALTH_URL)

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    for service in EXPECTED_SERVICES:
        assert data["services"][service] == "ok", f"Service '{service}' not ok: {data['services'][service]}"


@pytest.mark.e2e
async def test_health_response_structure(e2e_client: AsyncClient) -> None:
    """Health response contains 'status' and 'services' keys with exactly the 5 expected services."""
    resp = await e2e_client.get(HEALTH_URL)

    assert resp.status_code in (200, 503), f"Unexpected status code: {resp.status_code}"
    data = resp.json()

    assert "status" in data, "Response missing 'status' key"
    assert "services" in data, "Response missing 'services' key"
    assert isinstance(data["services"], dict), "'services' must be a dict"
    assert set(data["services"].keys()) == EXPECTED_SERVICES, f"Unexpected service keys: {set(data['services'].keys())}"
