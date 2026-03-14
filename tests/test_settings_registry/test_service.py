"""Tests for SettingsRegistryService — list, update, reset, load_overrides."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from app.settings_registry.registry import SETTING_REGISTRY
from app.settings_registry.service import (
    SettingsRegistryService,
    _coerce_value,
    _settings_env_default,
    _validate_range,
    load_setting_overrides_sync,
    load_setting_overrides_sync_safe,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_USER_ID = UUID("00000000-0000-0000-0000-000000000099")

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
    """Create a mock Settings with all setting attributes."""
    settings = MagicMock()
    # Set defaults for all registered settings
    for setting_name in SETTING_REGISTRY:
        meta = SETTING_REGISTRY[setting_name]
        default = _settings_env_default(setting_name, meta)
        setattr(settings, setting_name, default)
    # Also mock feature flag attributes
    for _, meta in SETTING_REGISTRY.items():
        if meta.requires_flag:
            setattr(settings, meta.requires_flag, False)
    return settings


# ---------------------------------------------------------------------------
# _coerce_value / _validate_range
# ---------------------------------------------------------------------------


class TestCoerceValue:
    def test_int_from_float(self):
        meta = SETTING_REGISTRY["retrieval_text_limit"]
        assert _coerce_value(40.0, meta) == 40
        assert isinstance(_coerce_value(40.0, meta), int)

    def test_float_from_int(self):
        meta = SETTING_REGISTRY["query_entity_threshold"]
        assert _coerce_value(1, meta) == 1.0
        assert isinstance(_coerce_value(1, meta), float)

    def test_int_from_string(self):
        meta = SETTING_REGISTRY["retrieval_text_limit"]
        assert _coerce_value("40", meta) == 40


class TestValidateRange:
    def test_valid_value(self):
        meta = SETTING_REGISTRY["retrieval_text_limit"]
        _validate_range(40, meta, "retrieval_text_limit")  # should not raise

    def test_below_min_raises(self):
        meta = SETTING_REGISTRY["retrieval_text_limit"]
        with pytest.raises(ValueError, match="below minimum"):
            _validate_range(0, meta, "retrieval_text_limit")

    def test_above_max_raises(self):
        meta = SETTING_REGISTRY["retrieval_text_limit"]
        with pytest.raises(ValueError, match="above maximum"):
            _validate_range(999, meta, "retrieval_text_limit")

    def test_float_range(self):
        meta = SETTING_REGISTRY["query_entity_threshold"]
        _validate_range(0.5, meta, "query_entity_threshold")  # should not raise
        with pytest.raises(ValueError, match="below minimum"):
            _validate_range(-0.1, meta, "query_entity_threshold")


# ---------------------------------------------------------------------------
# _settings_env_default
# ---------------------------------------------------------------------------


class TestSettingsEnvDefault:
    def test_int_default(self):
        meta = SETTING_REGISTRY["retrieval_text_limit"]
        result = _settings_env_default("retrieval_text_limit", meta)
        assert result == 40
        assert isinstance(result, int)

    def test_float_default(self):
        meta = SETTING_REGISTRY["query_entity_threshold"]
        result = _settings_env_default("query_entity_threshold", meta)
        assert result == 0.5
        assert isinstance(result, float)


# ---------------------------------------------------------------------------
# list_settings
# ---------------------------------------------------------------------------


class TestListSettings:
    @pytest.mark.asyncio
    async def test_returns_all_settings(self):
        db = _mock_db(rows=[])
        settings = _make_settings_mock()
        with patch(_PATCH_GET_SETTINGS, return_value=settings):
            items = await SettingsRegistryService.list_settings(db)

        assert len(items) == len(SETTING_REGISTRY)

    @pytest.mark.asyncio
    async def test_override_marked(self):
        override_row = {
            "setting_name": "retrieval_text_limit",
            "value": json.dumps(50),
            "updated_at": "2026-01-01T00:00:00Z",
            "updated_by": _USER_ID,
        }
        db = _mock_db(rows=[override_row])
        settings = _make_settings_mock()
        with patch(_PATCH_GET_SETTINGS, return_value=settings):
            items = await SettingsRegistryService.list_settings(db)

        item = next(i for i in items if i.setting_name == "retrieval_text_limit")
        assert item.is_override is True

    @pytest.mark.asyncio
    async def test_non_override_not_marked(self):
        db = _mock_db(rows=[])
        settings = _make_settings_mock()
        with patch(_PATCH_GET_SETTINGS, return_value=settings):
            items = await SettingsRegistryService.list_settings(db)

        item = next(i for i in items if i.setting_name == "retrieval_text_limit")
        assert item.is_override is False

    @pytest.mark.asyncio
    async def test_flag_enabled_field(self):
        db = _mock_db(rows=[])
        settings = _make_settings_mock()
        settings.enable_reranker = True
        with patch(_PATCH_GET_SETTINGS, return_value=settings):
            items = await SettingsRegistryService.list_settings(db)

        reranker_top_n = next(i for i in items if i.setting_name == "reranker_top_n")
        assert reranker_top_n.requires_flag == "enable_reranker"
        assert reranker_top_n.flag_enabled is True


# ---------------------------------------------------------------------------
# update_setting
# ---------------------------------------------------------------------------


class TestUpdateSetting:
    @pytest.mark.asyncio
    async def test_unknown_setting_raises(self):
        db = AsyncMock()
        with pytest.raises(ValueError, match="Unknown setting"):
            await SettingsRegistryService.update_setting(db, "nonexistent_setting", 42)

    @pytest.mark.asyncio
    async def test_updates_settings_singleton(self):
        from datetime import UTC, datetime

        row = {
            "setting_name": "retrieval_text_limit",
            "value": json.dumps(50),
            "updated_at": datetime(2026, 3, 14, tzinfo=UTC),
            "updated_by": _USER_ID,
        }
        db = _mock_db_upsert(row)

        settings = _make_settings_mock()
        settings.retrieval_text_limit = 40
        with patch(_PATCH_GET_SETTINGS, return_value=settings):
            result = await SettingsRegistryService.update_setting(db, "retrieval_text_limit", 50, user_id=_USER_ID)

        assert settings.retrieval_text_limit == 50
        assert result.value == 50
        assert result.is_override is True
        assert result.restart_required is False

    @pytest.mark.asyncio
    async def test_validates_range(self):
        db = AsyncMock()
        settings = _make_settings_mock()
        with (
            patch(_PATCH_GET_SETTINGS, return_value=settings),
            pytest.raises(ValueError, match="above maximum"),
        ):
            await SettingsRegistryService.update_setting(db, "retrieval_text_limit", 999)

    @pytest.mark.asyncio
    async def test_clears_di_caches_for_cache_clear_setting(self):
        from datetime import UTC, datetime

        row = {
            "setting_name": "reranker_top_n",
            "value": json.dumps(15),
            "updated_at": datetime(2026, 3, 14, tzinfo=UTC),
            "updated_by": _USER_ID,
        }
        db = _mock_db_upsert(row)

        settings = _make_settings_mock()
        settings.enable_reranker = True
        with (
            patch(_PATCH_GET_SETTINGS, return_value=settings),
            patch("app.settings_registry.service._clear_di_caches") as mock_clear,
        ):
            mock_clear.return_value = ["get_reranker", "get_retriever"]
            result = await SettingsRegistryService.update_setting(db, "reranker_top_n", 15, user_id=_USER_ID)

        mock_clear.assert_called_once()
        assert result.caches_cleared == ["get_reranker", "get_retriever"]

    @pytest.mark.asyncio
    async def test_restart_required_for_restart_setting(self):
        from datetime import UTC, datetime

        row = {
            "setting_name": "chunk_size",
            "value": json.dumps(1024),
            "updated_at": datetime(2026, 3, 14, tzinfo=UTC),
            "updated_by": _USER_ID,
        }
        db = _mock_db_upsert(row)

        settings = _make_settings_mock()
        with patch(_PATCH_GET_SETTINGS, return_value=settings):
            result = await SettingsRegistryService.update_setting(db, "chunk_size", 1024, user_id=_USER_ID)

        assert result.restart_required is True

    @pytest.mark.asyncio
    async def test_type_coercion_float_to_int(self):
        from datetime import UTC, datetime

        row = {
            "setting_name": "retrieval_text_limit",
            "value": json.dumps(30),
            "updated_at": datetime(2026, 3, 14, tzinfo=UTC),
            "updated_by": _USER_ID,
        }
        db = _mock_db_upsert(row)

        settings = _make_settings_mock()
        with patch(_PATCH_GET_SETTINGS, return_value=settings):
            result = await SettingsRegistryService.update_setting(db, "retrieval_text_limit", 30.0, user_id=_USER_ID)

        assert isinstance(result.value, int)
        assert result.value == 30


# ---------------------------------------------------------------------------
# reset_setting
# ---------------------------------------------------------------------------


class TestResetSetting:
    @pytest.mark.asyncio
    async def test_unknown_setting_raises(self):
        db = AsyncMock()
        with pytest.raises(ValueError, match="Unknown setting"):
            await SettingsRegistryService.reset_setting(db, "nonexistent_setting")

    @pytest.mark.asyncio
    async def test_reverts_to_env_default(self):
        db = AsyncMock()
        settings = _make_settings_mock()
        settings.retrieval_text_limit = 50  # was overridden
        with patch(_PATCH_GET_SETTINGS, return_value=settings):
            await SettingsRegistryService.reset_setting(db, "retrieval_text_limit")

        assert settings.retrieval_text_limit == 40  # env default

    @pytest.mark.asyncio
    async def test_executes_delete(self):
        db = AsyncMock()
        settings = _make_settings_mock()
        with patch(_PATCH_GET_SETTINGS, return_value=settings):
            await SettingsRegistryService.reset_setting(db, "retrieval_text_limit")

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
            await SettingsRegistryService.load_overrides_into_settings(db)

    @pytest.mark.asyncio
    async def test_applies_overrides(self):
        rows = [
            {"setting_name": "retrieval_text_limit", "value": json.dumps(50)},
            {"setting_name": "query_entity_threshold", "value": json.dumps(0.7)},
        ]
        db = _mock_db(rows=rows)
        settings = _make_settings_mock()
        settings.retrieval_text_limit = 40
        settings.query_entity_threshold = 0.5
        with patch(_PATCH_GET_SETTINGS, return_value=settings):
            await SettingsRegistryService.load_overrides_into_settings(db)

        assert settings.retrieval_text_limit == 50
        assert settings.query_entity_threshold == 0.7

    @pytest.mark.asyncio
    async def test_skips_unknown_settings(self):
        rows = [{"setting_name": "nonexistent_setting", "value": json.dumps(42)}]
        db = _mock_db(rows=rows)
        settings = _make_settings_mock()
        with patch(_PATCH_GET_SETTINGS, return_value=settings):
            await SettingsRegistryService.load_overrides_into_settings(db)

    @pytest.mark.asyncio
    async def test_skips_invalid_json(self):
        rows = [{"setting_name": "retrieval_text_limit", "value": "not-json{"}]
        db = _mock_db(rows=rows)
        settings = _make_settings_mock()
        settings.retrieval_text_limit = 40
        with patch(_PATCH_GET_SETTINGS, return_value=settings):
            await SettingsRegistryService.load_overrides_into_settings(db)

        # Should remain at original value
        assert settings.retrieval_text_limit == 40


# ---------------------------------------------------------------------------
# load_setting_overrides_sync / load_setting_overrides_sync_safe
# ---------------------------------------------------------------------------


def _mock_sync_engine(rows: list[dict] | None = None):
    """Create a mock sync engine that returns the given rows."""
    engine = MagicMock()
    conn = MagicMock()
    result = MagicMock()
    result.mappings.return_value.all.return_value = rows or []
    conn.execute.return_value = result
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    engine.connect.return_value = conn
    return engine


class TestLoadOverridesSync:
    def test_no_overrides(self):
        settings = _make_settings_mock()
        engine = _mock_sync_engine(rows=[])
        load_setting_overrides_sync(settings, engine)

    def test_applies_overrides(self):
        settings = _make_settings_mock()
        settings.retrieval_text_limit = 40
        engine = _mock_sync_engine(rows=[{"setting_name": "retrieval_text_limit", "value": json.dumps(50)}])
        load_setting_overrides_sync(settings, engine)
        assert settings.retrieval_text_limit == 50

    def test_skips_unknown_settings(self):
        settings = _make_settings_mock()
        engine = _mock_sync_engine(rows=[{"setting_name": "nonexistent_setting", "value": json.dumps(42)}])
        load_setting_overrides_sync(settings, engine)

    def test_db_error_propagates(self):
        settings = _make_settings_mock()
        engine = MagicMock()
        conn = MagicMock()
        conn.execute.side_effect = RuntimeError("connection refused")
        conn.__enter__ = MagicMock(return_value=conn)
        conn.__exit__ = MagicMock(return_value=False)
        engine.connect.return_value = conn
        with pytest.raises(RuntimeError, match="connection refused"):
            load_setting_overrides_sync(settings, engine)


class TestLoadOverridesSyncSafe:
    def test_suppresses_db_error(self):
        settings = _make_settings_mock()
        engine = MagicMock()
        conn = MagicMock()
        conn.execute.side_effect = RuntimeError("connection refused")
        conn.__enter__ = MagicMock(return_value=conn)
        conn.__exit__ = MagicMock(return_value=False)
        engine.connect.return_value = conn
        # Should not raise
        load_setting_overrides_sync_safe(settings, engine)
