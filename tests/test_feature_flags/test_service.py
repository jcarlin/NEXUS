"""Tests for FeatureFlagService — list, update, reset, load_overrides."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from app.feature_flags.registry import FLAG_REGISTRY
from app.feature_flags.service import FeatureFlagService, settings_env_default

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_USER_ID = UUID("00000000-0000-0000-0000-000000000099")

# Patch target: get_settings is imported inside methods from app.dependencies
_PATCH_GET_SETTINGS = "app.dependencies.get_settings"


def _mock_db(rows: list[dict] | None = None):
    """Create a mock AsyncSession that returns the given rows."""
    db = AsyncMock()
    result = MagicMock()
    if rows is not None:
        result.mappings.return_value.all.return_value = rows
    else:
        result.mappings.return_value.all.return_value = []
    db.execute.return_value = result
    return db


def _mock_db_upsert(row: dict):
    """Mock DB that returns a single row from an UPSERT."""
    db = AsyncMock()
    result = MagicMock()
    result.mappings.return_value.one.return_value = row
    db.execute.return_value = result
    return db


def _make_settings_mock():
    """Create a mock Settings with all enable_* attributes."""
    settings = MagicMock()
    for flag_name in FLAG_REGISTRY:
        setattr(settings, flag_name, False)
    return settings


# ---------------------------------------------------------------------------
# settings_env_default
# ---------------------------------------------------------------------------


class TestSettingsEnvDefault:
    def test_reranker_default_true(self):
        assert settings_env_default("enable_reranker") is True

    def test_sparse_embeddings_default_false(self):
        assert settings_env_default("enable_sparse_embeddings") is False

    def test_unknown_flag_returns_false(self):
        assert settings_env_default("enable_nonexistent_flag") is False


# ---------------------------------------------------------------------------
# list_flags
# ---------------------------------------------------------------------------


class TestListFlags:
    @pytest.mark.asyncio
    async def test_returns_all_flags(self):
        db = _mock_db(rows=[])
        settings = _make_settings_mock()
        with patch(_PATCH_GET_SETTINGS, return_value=settings):
            items = await FeatureFlagService.list_flags(db)

        assert len(items) == len(FLAG_REGISTRY)

    @pytest.mark.asyncio
    async def test_override_marked(self):
        override_row = {
            "flag_name": "enable_reranker",
            "enabled": False,
            "updated_at": "2026-01-01T00:00:00Z",
            "updated_by": _USER_ID,
        }
        db = _mock_db(rows=[override_row])
        settings = _make_settings_mock()
        with patch(_PATCH_GET_SETTINGS, return_value=settings):
            items = await FeatureFlagService.list_flags(db)

        reranker = next(i for i in items if i.flag_name == "enable_reranker")
        assert reranker.is_override is True

    @pytest.mark.asyncio
    async def test_non_override_not_marked(self):
        db = _mock_db(rows=[])
        settings = _make_settings_mock()
        for flag_name in FLAG_REGISTRY:
            setattr(settings, flag_name, True)
        with patch(_PATCH_GET_SETTINGS, return_value=settings):
            items = await FeatureFlagService.list_flags(db)

        reranker = next(i for i in items if i.flag_name == "enable_reranker")
        assert reranker.is_override is False
        assert reranker.enabled is True


# ---------------------------------------------------------------------------
# update_flag
# ---------------------------------------------------------------------------


class TestUpdateFlag:
    @pytest.mark.asyncio
    async def test_unknown_flag_raises(self):
        db = AsyncMock()
        with pytest.raises(ValueError, match="Unknown feature flag"):
            await FeatureFlagService.update_flag(db, "enable_nonexistent", True)

    @pytest.mark.asyncio
    async def test_updates_settings_singleton(self):
        from datetime import UTC, datetime

        row = {
            "flag_name": "enable_ai_audit_logging",
            "enabled": False,
            "updated_at": datetime(2026, 3, 12, tzinfo=UTC),
            "updated_by": _USER_ID,
        }
        db = _mock_db_upsert(row)

        settings = _make_settings_mock()
        settings.enable_ai_audit_logging = True
        with patch(_PATCH_GET_SETTINGS, return_value=settings):
            result = await FeatureFlagService.update_flag(db, "enable_ai_audit_logging", False, user_id=_USER_ID)

        # Settings singleton should have been mutated
        assert settings.enable_ai_audit_logging is False
        assert result.enabled is False
        assert result.is_override is True
        assert result.restart_required is False

    @pytest.mark.asyncio
    async def test_clears_di_caches_for_cache_clear_flag(self):
        from datetime import UTC, datetime

        row = {
            "flag_name": "enable_reranker",
            "enabled": True,
            "updated_at": datetime(2026, 3, 12, tzinfo=UTC),
            "updated_by": _USER_ID,
        }
        db = _mock_db_upsert(row)

        settings = _make_settings_mock()
        settings.enable_reranker = False
        with (
            patch(_PATCH_GET_SETTINGS, return_value=settings),
            patch("app.feature_flags.service._clear_di_caches") as mock_clear,
        ):
            mock_clear.return_value = ["get_reranker", "get_retriever", "get_query_graph"]
            result = await FeatureFlagService.update_flag(db, "enable_reranker", True, user_id=_USER_ID)

        mock_clear.assert_called_once()
        assert result.caches_cleared == ["get_reranker", "get_retriever", "get_query_graph"]

    @pytest.mark.asyncio
    async def test_restart_required_for_restart_flag(self):
        from datetime import UTC, datetime

        row = {
            "flag_name": "enable_google_drive",
            "enabled": True,
            "updated_at": datetime(2026, 3, 12, tzinfo=UTC),
            "updated_by": _USER_ID,
        }
        db = _mock_db_upsert(row)

        settings = _make_settings_mock()
        settings.enable_google_drive = False
        with patch(_PATCH_GET_SETTINGS, return_value=settings):
            result = await FeatureFlagService.update_flag(db, "enable_google_drive", True, user_id=_USER_ID)

        assert result.restart_required is True


# ---------------------------------------------------------------------------
# reset_flag
# ---------------------------------------------------------------------------


class TestResetFlag:
    @pytest.mark.asyncio
    async def test_unknown_flag_raises(self):
        db = AsyncMock()
        with pytest.raises(ValueError, match="Unknown feature flag"):
            await FeatureFlagService.reset_flag(db, "enable_nonexistent")

    @pytest.mark.asyncio
    async def test_reverts_to_env_default(self):
        db = AsyncMock()
        settings = _make_settings_mock()
        settings.enable_reranker = False  # was overridden to False
        with patch(_PATCH_GET_SETTINGS, return_value=settings):
            await FeatureFlagService.reset_flag(db, "enable_reranker")

        # Should revert to env default (True for reranker)
        assert settings.enable_reranker is True

    @pytest.mark.asyncio
    async def test_executes_delete(self):
        db = AsyncMock()
        settings = _make_settings_mock()
        with patch(_PATCH_GET_SETTINGS, return_value=settings):
            await FeatureFlagService.reset_flag(db, "enable_reranker")

        db.execute.assert_called_once()


# ---------------------------------------------------------------------------
# load_overrides_into_settings
# ---------------------------------------------------------------------------


class TestLoadOverrides:
    @pytest.mark.asyncio
    async def test_no_overrides(self):
        db = _mock_db(rows=[])
        settings = _make_settings_mock()
        with patch(_PATCH_GET_SETTINGS, return_value=settings):
            await FeatureFlagService.load_overrides_into_settings(db)

    @pytest.mark.asyncio
    async def test_applies_overrides(self):
        rows = [
            {"flag_name": "enable_reranker", "enabled": False},
            {"flag_name": "enable_sparse_embeddings", "enabled": True},
        ]
        db = _mock_db(rows=rows)
        settings = _make_settings_mock()
        settings.enable_reranker = True
        settings.enable_sparse_embeddings = False
        with patch(_PATCH_GET_SETTINGS, return_value=settings):
            await FeatureFlagService.load_overrides_into_settings(db)

        assert settings.enable_reranker is False
        assert settings.enable_sparse_embeddings is True

    @pytest.mark.asyncio
    async def test_skips_unknown_flags(self):
        rows = [{"flag_name": "enable_nonexistent_flag", "enabled": True}]
        db = _mock_db(rows=rows)
        settings = _make_settings_mock()
        with patch(_PATCH_GET_SETTINGS, return_value=settings):
            # Should not raise
            await FeatureFlagService.load_overrides_into_settings(db)
