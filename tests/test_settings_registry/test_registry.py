"""Tests for SettingMeta registry — validation and type correctness."""

from __future__ import annotations

from app.config import Settings
from app.settings_registry.registry import SETTING_REGISTRY, validate_registry
from app.settings_registry.schemas import SettingType


class TestValidateRegistry:
    def test_validate_registry_passes(self):
        """All registry entries map to real Settings fields."""
        validate_registry()

    def test_all_keys_are_settings_fields(self):
        settings_fields = set(Settings.model_fields.keys())
        for setting_name in SETTING_REGISTRY:
            assert setting_name in settings_fields, f"{setting_name} not in Settings"

    def test_no_enable_flags_in_registry(self):
        """Settings registry is for numeric/string tuning, not boolean feature flags."""
        for setting_name in SETTING_REGISTRY:
            assert not setting_name.startswith(
                "enable_"
            ), f"{setting_name} looks like a feature flag — use FLAG_REGISTRY instead"

    def test_int_settings_have_int_defaults(self):
        for name, meta in SETTING_REGISTRY.items():
            if meta.setting_type == SettingType.INT:
                field_info = Settings.model_fields.get(name)
                assert field_info is not None
                assert isinstance(
                    field_info.default, int
                ), f"{name}: expected int default, got {type(field_info.default).__name__}"

    def test_float_settings_have_numeric_defaults(self):
        for name, meta in SETTING_REGISTRY.items():
            if meta.setting_type == SettingType.FLOAT:
                field_info = Settings.model_fields.get(name)
                assert field_info is not None
                assert isinstance(
                    field_info.default, int | float
                ), f"{name}: expected numeric default, got {type(field_info.default).__name__}"

    def test_requires_flag_references_exist(self):
        """Every requires_flag must also be a Settings field."""
        settings_fields = set(Settings.model_fields.keys())
        for name, meta in SETTING_REGISTRY.items():
            if meta.requires_flag:
                assert (
                    meta.requires_flag in settings_fields
                ), f"{name}: requires_flag '{meta.requires_flag}' not found in Settings"

    def test_min_max_consistent(self):
        """Min should be <= max when both are specified."""
        for name, meta in SETTING_REGISTRY.items():
            if meta.min_value is not None and meta.max_value is not None:
                assert (
                    meta.min_value <= meta.max_value
                ), f"{name}: min_value ({meta.min_value}) > max_value ({meta.max_value})"

    def test_registry_not_empty(self):
        assert len(SETTING_REGISTRY) > 0
