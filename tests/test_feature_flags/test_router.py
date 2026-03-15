"""Tests for feature flag admin API endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
from httpx import AsyncClient

from app.feature_flags.schemas import (
    FeatureFlagDetail,
    FeatureFlagUpdateResponse,
    FlagCategory,
    FlagRiskLevel,
)

_USER_ID = UUID("00000000-0000-0000-0000-000000000099")


def _make_flag_detail(**overrides) -> FeatureFlagDetail:
    defaults = {
        "flag_name": "enable_reranker",
        "display_name": "Cross-Encoder Reranker",
        "description": "Test",
        "category": FlagCategory.RETRIEVAL,
        "risk_level": FlagRiskLevel.CACHE_CLEAR,
        "enabled": True,
        "is_override": False,
        "env_default": True,
    }
    defaults.update(overrides)
    return FeatureFlagDetail(**defaults)


# ---------------------------------------------------------------------------
# GET /admin/feature-flags
# ---------------------------------------------------------------------------


class TestListFlags:
    @pytest.mark.asyncio
    async def test_list_returns_flags(self, client: AsyncClient):
        flags = [_make_flag_detail()]
        with patch(
            "app.feature_flags.router.FeatureFlagService.list_flags",
            new_callable=AsyncMock,
            return_value=flags,
        ):
            resp = await client.get("/api/v1/admin/feature-flags")

        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert len(data["items"]) == 1
        assert data["items"][0]["flag_name"] == "enable_reranker"

    @pytest.mark.asyncio
    async def test_list_requires_admin(self, unauthed_client: AsyncClient):
        resp = await unauthed_client.get("/api/v1/admin/feature-flags")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PUT /admin/feature-flags/{flag_name}
# ---------------------------------------------------------------------------


class TestUpdateFlag:
    @pytest.mark.asyncio
    async def test_update_flag(self, client: AsyncClient):
        response_data = FeatureFlagUpdateResponse(
            flag_name="enable_reranker",
            display_name="Cross-Encoder Reranker",
            description="Test",
            category=FlagCategory.RETRIEVAL,
            risk_level=FlagRiskLevel.CACHE_CLEAR,
            enabled=False,
            is_override=True,
            env_default=True,
            updated_at=datetime(2026, 3, 12, tzinfo=UTC),
            updated_by=_USER_ID,
            caches_cleared=["get_reranker"],
            restart_required=False,
        )
        with patch(
            "app.feature_flags.router.FeatureFlagService.update_flag",
            new_callable=AsyncMock,
            return_value=response_data,
        ):
            resp = await client.put(
                "/api/v1/admin/feature-flags/enable_reranker",
                json={"enabled": False},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["enabled"] is False
        assert data["is_override"] is True
        assert data["caches_cleared"] == ["get_reranker"]

    @pytest.mark.asyncio
    async def test_update_unknown_flag_400(self, client: AsyncClient):
        with patch(
            "app.feature_flags.router.FeatureFlagService.update_flag",
            new_callable=AsyncMock,
            side_effect=ValueError("Unknown feature flag: enable_fake"),
        ):
            resp = await client.put(
                "/api/v1/admin/feature-flags/enable_fake",
                json={"enabled": True},
            )

        assert resp.status_code == 400
        assert "Unknown feature flag" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_update_requires_admin(self, unauthed_client: AsyncClient):
        resp = await unauthed_client.put(
            "/api/v1/admin/feature-flags/enable_reranker",
            json={"enabled": False},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /admin/feature-flags/{flag_name}
# ---------------------------------------------------------------------------


class TestResetFlag:
    @pytest.mark.asyncio
    async def test_reset_flag(self, client: AsyncClient):
        with patch(
            "app.feature_flags.router.FeatureFlagService.reset_flag",
            new_callable=AsyncMock,
        ):
            resp = await client.delete("/api/v1/admin/feature-flags/enable_reranker")

        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_reset_unknown_flag_400(self, client: AsyncClient):
        with patch(
            "app.feature_flags.router.FeatureFlagService.reset_flag",
            new_callable=AsyncMock,
            side_effect=ValueError("Unknown feature flag: enable_fake"),
        ):
            resp = await client.delete("/api/v1/admin/feature-flags/enable_fake")

        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_reset_requires_admin(self, unauthed_client: AsyncClient):
        resp = await unauthed_client.delete("/api/v1/admin/feature-flags/enable_reranker")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /config/features (expanded endpoint)
# ---------------------------------------------------------------------------


class TestConfigFeaturesEndpoint:
    @pytest.mark.asyncio
    async def test_returns_all_flags(self, client: AsyncClient):
        resp = await client.get("/api/v1/config/features")
        assert resp.status_code == 200
        data = resp.json()
        assert "reranker" in data
        assert "visual_embeddings" in data
        assert "agentic_pipeline" in data
        assert "google_drive" in data
        # All values must be booleans
        assert all(isinstance(v, bool) for v in data.values())
        assert len(data) >= 23  # at least the original flags
