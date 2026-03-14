"""Tests for settings registry admin API endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
from httpx import AsyncClient

from app.settings_registry.schemas import (
    SettingCategory,
    SettingDetail,
    SettingRiskLevel,
    SettingType,
    SettingUpdateResponse,
)

_USER_ID = UUID("00000000-0000-0000-0000-000000000099")


def _make_setting_detail(**overrides) -> SettingDetail:
    defaults = {
        "setting_name": "retrieval_text_limit",
        "display_name": "Text Retrieval Limit",
        "description": "Maximum number of text chunks retrieved per query.",
        "category": SettingCategory.RETRIEVAL,
        "setting_type": SettingType.INT,
        "risk_level": SettingRiskLevel.SAFE,
        "value": 40,
        "env_default": 40,
        "min_value": 1,
        "max_value": 100,
        "unit": "chunks",
        "is_override": False,
    }
    defaults.update(overrides)
    return SettingDetail(**defaults)


# ---------------------------------------------------------------------------
# GET /admin/settings
# ---------------------------------------------------------------------------


class TestListSettings:
    @pytest.mark.asyncio
    async def test_list_returns_settings(self, client: AsyncClient):
        items = [_make_setting_detail()]
        with patch(
            "app.settings_registry.router.SettingsRegistryService.list_settings",
            new_callable=AsyncMock,
            return_value=items,
        ):
            resp = await client.get("/api/v1/admin/settings")

        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert len(data["items"]) == 1
        assert data["items"][0]["setting_name"] == "retrieval_text_limit"

    @pytest.mark.asyncio
    async def test_list_requires_admin(self, unauthed_client: AsyncClient):
        resp = await unauthed_client.get("/api/v1/admin/settings")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PUT /admin/settings/{setting_name}
# ---------------------------------------------------------------------------


class TestUpdateSetting:
    @pytest.mark.asyncio
    async def test_update_setting(self, client: AsyncClient):
        response_data = SettingUpdateResponse(
            setting_name="retrieval_text_limit",
            display_name="Text Retrieval Limit",
            description="Maximum number of text chunks retrieved per query.",
            category=SettingCategory.RETRIEVAL,
            setting_type=SettingType.INT,
            risk_level=SettingRiskLevel.SAFE,
            value=50,
            env_default=40,
            min_value=1,
            max_value=100,
            unit="chunks",
            is_override=True,
            updated_at=datetime(2026, 3, 14, tzinfo=UTC),
            updated_by=_USER_ID,
            caches_cleared=[],
            restart_required=False,
        )
        with patch(
            "app.settings_registry.router.SettingsRegistryService.update_setting",
            new_callable=AsyncMock,
            return_value=response_data,
        ):
            resp = await client.put(
                "/api/v1/admin/settings/retrieval_text_limit",
                json={"value": 50},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["value"] == 50
        assert data["is_override"] is True

    @pytest.mark.asyncio
    async def test_update_unknown_setting_400(self, client: AsyncClient):
        with patch(
            "app.settings_registry.router.SettingsRegistryService.update_setting",
            new_callable=AsyncMock,
            side_effect=ValueError("Unknown setting: fake_setting"),
        ):
            resp = await client.put(
                "/api/v1/admin/settings/fake_setting",
                json={"value": 42},
            )

        assert resp.status_code == 400
        assert "Unknown setting" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_update_out_of_range_400(self, client: AsyncClient):
        with patch(
            "app.settings_registry.router.SettingsRegistryService.update_setting",
            new_callable=AsyncMock,
            side_effect=ValueError("retrieval_text_limit: value 999 above maximum 100"),
        ):
            resp = await client.put(
                "/api/v1/admin/settings/retrieval_text_limit",
                json={"value": 999},
            )

        assert resp.status_code == 400
        assert "above maximum" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_update_requires_admin(self, unauthed_client: AsyncClient):
        resp = await unauthed_client.put(
            "/api/v1/admin/settings/retrieval_text_limit",
            json={"value": 50},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /admin/settings/{setting_name}
# ---------------------------------------------------------------------------


class TestResetSetting:
    @pytest.mark.asyncio
    async def test_reset_setting(self, client: AsyncClient):
        with patch(
            "app.settings_registry.router.SettingsRegistryService.reset_setting",
            new_callable=AsyncMock,
        ):
            resp = await client.delete("/api/v1/admin/settings/retrieval_text_limit")

        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_reset_unknown_setting_400(self, client: AsyncClient):
        with patch(
            "app.settings_registry.router.SettingsRegistryService.reset_setting",
            new_callable=AsyncMock,
            side_effect=ValueError("Unknown setting: fake_setting"),
        ):
            resp = await client.delete("/api/v1/admin/settings/fake_setting")

        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_reset_requires_admin(self, unauthed_client: AsyncClient):
        resp = await unauthed_client.delete("/api/v1/admin/settings/retrieval_text_limit")
        assert resp.status_code == 401
