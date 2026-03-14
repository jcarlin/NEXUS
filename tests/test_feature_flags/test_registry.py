"""Tests for feature flag registry metadata."""

from __future__ import annotations

import pytest

from app.config import Settings
from app.feature_flags.registry import FLAG_REGISTRY, FlagMeta
from app.feature_flags.schemas import FlagCategory, FlagRiskLevel


class TestFlagRegistry:
    """Validate registry metadata integrity."""

    def test_registry_not_empty(self):
        assert len(FLAG_REGISTRY) > 0

    def test_all_flags_map_to_settings_fields(self):
        """Every registry key must be a real Settings attribute."""
        settings_fields = set(Settings.model_fields.keys())
        for flag_name in FLAG_REGISTRY:
            assert flag_name in settings_fields, f"{flag_name} not in Settings"

    def test_all_settings_enable_flags_in_registry(self):
        """Every enable_* field in Settings should be in the registry."""
        enable_fields = {k for k in Settings.model_fields if k.startswith("enable_")}
        registry_keys = set(FLAG_REGISTRY.keys())
        missing = enable_fields - registry_keys
        assert not missing, f"Settings fields missing from registry: {missing}"

    def test_all_entries_are_flag_meta(self):
        for flag_name, meta in FLAG_REGISTRY.items():
            assert isinstance(meta, FlagMeta), f"{flag_name} is not FlagMeta"

    def test_valid_categories(self):
        valid = set(FlagCategory)
        for flag_name, meta in FLAG_REGISTRY.items():
            assert meta.category in valid, f"{flag_name} has invalid category: {meta.category}"

    def test_valid_risk_levels(self):
        valid = set(FlagRiskLevel)
        for flag_name, meta in FLAG_REGISTRY.items():
            assert meta.risk_level in valid, f"{flag_name} has invalid risk_level: {meta.risk_level}"

    def test_display_names_not_empty(self):
        for flag_name, meta in FLAG_REGISTRY.items():
            assert meta.display_name.strip(), f"{flag_name} has empty display_name"

    def test_descriptions_not_empty(self):
        for flag_name, meta in FLAG_REGISTRY.items():
            assert meta.description.strip(), f"{flag_name} has empty description"

    def test_di_caches_only_on_cache_clear_flags(self):
        """Flags with di_caches should have risk_level=cache_clear."""
        for flag_name, meta in FLAG_REGISTRY.items():
            if meta.di_caches:
                assert (
                    meta.risk_level == FlagRiskLevel.CACHE_CLEAR
                ), f"{flag_name} has di_caches but risk_level={meta.risk_level}"

    def test_di_cache_names_exist_in_dependencies(self):
        """All di_cache names should reference real functions in dependencies."""
        from app import dependencies

        for flag_name, meta in FLAG_REGISTRY.items():
            for cache_name in meta.di_caches:
                assert hasattr(dependencies, cache_name), f"{flag_name} references non-existent DI cache: {cache_name}"

    def test_expected_flag_count(self):
        """Registry should have 23 flags matching all enable_* Settings fields."""
        enable_fields = {k for k in Settings.model_fields if k.startswith("enable_")}
        assert len(FLAG_REGISTRY) == len(enable_fields)

    @pytest.mark.parametrize(
        "flag_name,expected_risk",
        [
            ("enable_reranker", FlagRiskLevel.CACHE_CLEAR),
            ("enable_agentic_pipeline", FlagRiskLevel.CACHE_CLEAR),
            ("enable_google_drive", FlagRiskLevel.RESTART),
            ("enable_sso", FlagRiskLevel.CACHE_CLEAR),
            ("enable_ai_audit_logging", FlagRiskLevel.SAFE),
            ("enable_citation_verification", FlagRiskLevel.SAFE),
        ],
    )
    def test_specific_risk_levels(self, flag_name: str, expected_risk: FlagRiskLevel):
        assert FLAG_REGISTRY[flag_name].risk_level == expected_risk
