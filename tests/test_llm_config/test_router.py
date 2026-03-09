"""Tests for LLM config admin router endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient

from app.auth.schemas import UserRecord
from app.llm_config.schemas import (
    CostEstimateResponse,
    LLMConfigOverview,
    LLMProviderResponse,
    LLMProviderType,
    LLMTier,
    LLMTierConfigResponse,
    OllamaModel,
    TestConnectionResponse,
    TierCostEstimate,
)

_NOW = datetime(2026, 1, 1, tzinfo=UTC)
_PROVIDER_ID = uuid4()

_FAKE_PROVIDER = LLMProviderResponse(
    id=_PROVIDER_ID,
    provider=LLMProviderType.ANTHROPIC,
    label="Test Anthropic",
    api_key_set=True,
    base_url="",
    is_active=True,
    created_at=_NOW,
    updated_at=_NOW,
)

_REVIEWER_USER = UserRecord(
    id=UUID("00000000-0000-0000-0000-000000000077"),
    email="reviewer@nexus.dev",
    full_name="Doc Reviewer",
    role="reviewer",
    is_active=True,
    created_at=_NOW,
)


def _mock_db_override(app):
    """Inject a mock DB session into the app's dependency overrides."""
    from app.dependencies import get_db

    mock_session = AsyncMock()

    async def mock_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = mock_get_db
    return mock_session


def _set_reviewer(app):
    """Override current user to be a reviewer (non-admin)."""
    from app.auth.middleware import get_current_user

    app.dependency_overrides[get_current_user] = lambda: _REVIEWER_USER


def _restore_admin(app):
    """Restore admin user after non-admin test."""
    from app.auth.middleware import get_current_user
    from tests.conftest import _TEST_USER

    app.dependency_overrides[get_current_user] = lambda: _TEST_USER


# ---------------------------------------------------------------------------
# GET /admin/llm-config (overview)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_overview_admin_200(client: AsyncClient) -> None:
    overview = LLMConfigOverview(
        providers=[_FAKE_PROVIDER],
        tiers=[
            LLMTierConfigResponse(tier=LLMTier.QUERY, model="claude-sonnet-4-5-20250929", is_env_default=True),
            LLMTierConfigResponse(tier=LLMTier.ANALYSIS, model="claude-sonnet-4-5-20250929", is_env_default=True),
            LLMTierConfigResponse(tier=LLMTier.INGESTION, model="claude-sonnet-4-5-20250929", is_env_default=True),
        ],
        env_defaults={
            "query": "anthropic/claude-sonnet-4-5-20250929",
            "analysis": "anthropic/claude-sonnet-4-5-20250929",
            "ingestion": "anthropic/claude-sonnet-4-5-20250929",
        },
    )
    _mock_db_override(client._transport.app)

    with patch("app.llm_config.router.LLMConfigService.get_overview", new_callable=AsyncMock, return_value=overview):
        resp = await client.get("/api/v1/admin/llm-config")

    assert resp.status_code == 200
    body = resp.json()
    assert "providers" in body
    assert "tiers" in body
    assert len(body["providers"]) == 1


@pytest.mark.asyncio
async def test_overview_non_admin_403(client: AsyncClient) -> None:
    app = client._transport.app
    _set_reviewer(app)
    try:
        resp = await client.get("/api/v1/admin/llm-config")
    finally:
        _restore_admin(app)
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /admin/llm-config/providers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_provider_201(client: AsyncClient) -> None:
    _mock_db_override(client._transport.app)

    with patch(
        "app.llm_config.router.LLMConfigService.create_provider", new_callable=AsyncMock, return_value=_FAKE_PROVIDER
    ):
        resp = await client.post(
            "/api/v1/admin/llm-config/providers",
            json={"provider": "anthropic", "label": "Test Anthropic", "api_key": "sk-test"},
        )

    assert resp.status_code == 201
    assert resp.json()["label"] == "Test Anthropic"


@pytest.mark.asyncio
async def test_create_provider_non_admin_403(client: AsyncClient) -> None:
    app = client._transport.app
    _set_reviewer(app)
    try:
        resp = await client.post(
            "/api/v1/admin/llm-config/providers",
            json={"provider": "anthropic", "label": "Test"},
        )
    finally:
        _restore_admin(app)
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# PATCH /admin/llm-config/providers/{id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_provider_200(client: AsyncClient) -> None:
    _mock_db_override(client._transport.app)
    updated = _FAKE_PROVIDER.model_copy(update={"label": "Updated"})

    with patch("app.llm_config.router.LLMConfigService.update_provider", new_callable=AsyncMock, return_value=updated):
        resp = await client.patch(
            f"/api/v1/admin/llm-config/providers/{_PROVIDER_ID}",
            json={"label": "Updated"},
        )

    assert resp.status_code == 200
    assert resp.json()["label"] == "Updated"


@pytest.mark.asyncio
async def test_update_provider_404(client: AsyncClient) -> None:
    _mock_db_override(client._transport.app)

    with patch("app.llm_config.router.LLMConfigService.update_provider", new_callable=AsyncMock, return_value=None):
        resp = await client.patch(
            f"/api/v1/admin/llm-config/providers/{uuid4()}",
            json={"label": "X"},
        )

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /admin/llm-config/providers/{id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deactivate_provider_204(client: AsyncClient) -> None:
    _mock_db_override(client._transport.app)

    with patch("app.llm_config.router.LLMConfigService.deactivate_provider", new_callable=AsyncMock, return_value=True):
        resp = await client.delete(f"/api/v1/admin/llm-config/providers/{_PROVIDER_ID}")

    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_deactivate_provider_404(client: AsyncClient) -> None:
    _mock_db_override(client._transport.app)

    with patch(
        "app.llm_config.router.LLMConfigService.deactivate_provider", new_callable=AsyncMock, return_value=False
    ):
        resp = await client.delete(f"/api/v1/admin/llm-config/providers/{uuid4()}")

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /admin/llm-config/providers/{id}/test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_test_connection_200(client: AsyncClient) -> None:
    _mock_db_override(client._transport.app)
    conn_result = TestConnectionResponse(success=True, latency_ms=42)

    with patch(
        "app.llm_config.router.LLMConfigService.test_connection", new_callable=AsyncMock, return_value=conn_result
    ):
        resp = await client.post(f"/api/v1/admin/llm-config/providers/{_PROVIDER_ID}/test")

    assert resp.status_code == 200
    assert resp.json()["success"] is True
    assert resp.json()["latency_ms"] == 42


# ---------------------------------------------------------------------------
# PUT /admin/llm-config/tiers/{tier}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_tier_config_200(client: AsyncClient) -> None:
    _mock_db_override(client._transport.app)
    tier_resp = LLMTierConfigResponse(
        tier=LLMTier.QUERY,
        provider_id=_PROVIDER_ID,
        provider_label="OpenAI",
        provider_type=LLMProviderType.OPENAI,
        model="gpt-4o",
        updated_at=_NOW,
        is_env_default=False,
    )

    with patch(
        "app.llm_config.router.LLMConfigService.set_tier_config", new_callable=AsyncMock, return_value=tier_resp
    ):
        resp = await client.put(
            "/api/v1/admin/llm-config/tiers/query",
            json={"provider_id": str(_PROVIDER_ID), "model": "gpt-4o"},
        )

    assert resp.status_code == 200
    assert resp.json()["model"] == "gpt-4o"
    assert resp.json()["is_env_default"] is False


@pytest.mark.asyncio
async def test_set_tier_config_bad_provider_400(client: AsyncClient) -> None:
    _mock_db_override(client._transport.app)

    with patch(
        "app.llm_config.router.LLMConfigService.set_tier_config",
        new_callable=AsyncMock,
        side_effect=ValueError("Provider not found or inactive"),
    ):
        resp = await client.put(
            "/api/v1/admin/llm-config/tiers/query",
            json={"provider_id": str(uuid4()), "model": "gpt-4o"},
        )

    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# DELETE /admin/llm-config/tiers/{tier}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_tier_config_204(client: AsyncClient) -> None:
    _mock_db_override(client._transport.app)

    with patch("app.llm_config.router.LLMConfigService.delete_tier_config", new_callable=AsyncMock, return_value=True):
        resp = await client.delete("/api/v1/admin/llm-config/tiers/query")

    assert resp.status_code == 204


# ---------------------------------------------------------------------------
# GET /admin/llm-config/ollama/models
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_discover_ollama_models_200(client: AsyncClient) -> None:
    models = [OllamaModel(name="llama3:latest", size=4_000_000_000)]

    with patch(
        "app.llm_config.router.LLMConfigService.discover_ollama_models", new_callable=AsyncMock, return_value=models
    ):
        resp = await client.get("/api/v1/admin/llm-config/ollama/models")

    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 1
    assert resp.json()["items"][0]["name"] == "llama3:latest"


# ---------------------------------------------------------------------------
# GET /admin/llm-config/cost-estimate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cost_estimate_200(client: AsyncClient) -> None:
    _mock_db_override(client._transport.app)
    estimate = CostEstimateResponse(
        period_days=30,
        tiers=[
            TierCostEstimate(
                tier=LLMTier.QUERY, model="gpt-4o", input_tokens=1000, output_tokens=500, estimated_cost_usd=0.01
            ),
        ],
        total_cost_usd=0.01,
    )

    with patch("app.llm_config.router.LLMConfigService.estimate_costs", new_callable=AsyncMock, return_value=estimate):
        resp = await client.get("/api/v1/admin/llm-config/cost-estimate?period_days=30")

    assert resp.status_code == 200
    assert resp.json()["period_days"] == 30
    assert resp.json()["total_cost_usd"] == 0.01


# ---------------------------------------------------------------------------
# POST /admin/llm-config/apply
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apply_config_204(client: AsyncClient) -> None:
    with (
        patch("app.llm_config.resolver.clear_cache"),
        patch("app.dependencies.get_llm"),
        patch("app.dependencies.get_query_graph"),
    ):
        resp = await client.post("/api/v1/admin/llm-config/apply")

    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_apply_non_admin_403(client: AsyncClient) -> None:
    app = client._transport.app
    _set_reviewer(app)
    try:
        resp = await client.post("/api/v1/admin/llm-config/apply")
    finally:
        _restore_admin(app)
    assert resp.status_code == 403
