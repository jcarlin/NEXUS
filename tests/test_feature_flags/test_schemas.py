"""Tests for feature flag Pydantic schemas."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from app.feature_flags.schemas import (
    FeatureFlagDetail,
    FeatureFlagListResponse,
    FeatureFlagUpdateRequest,
    FeatureFlagUpdateResponse,
    FlagCategory,
    FlagRiskLevel,
)


class TestFlagCategory:
    def test_all_values(self):
        expected = {"retrieval", "ingestion", "query", "entity_graph", "intelligence", "audit", "integrations", "pages"}
        assert set(FlagCategory) == expected


class TestFlagRiskLevel:
    def test_all_values(self):
        assert set(FlagRiskLevel) == {"safe", "cache_clear", "restart"}


class TestFeatureFlagDetail:
    def test_serialization(self):
        detail = FeatureFlagDetail(
            flag_name="enable_reranker",
            display_name="Cross-Encoder Reranker",
            description="Test description",
            category=FlagCategory.RETRIEVAL,
            risk_level=FlagRiskLevel.CACHE_CLEAR,
            enabled=True,
            is_override=False,
            env_default=True,
        )
        data = detail.model_dump()
        assert data["flag_name"] == "enable_reranker"
        assert data["enabled"] is True
        assert data["is_override"] is False
        assert data["category"] == "retrieval"
        assert data["risk_level"] == "cache_clear"

    def test_with_override_fields(self):
        uid = UUID("00000000-0000-0000-0000-000000000099")
        now = datetime(2026, 3, 12, tzinfo=UTC)
        detail = FeatureFlagDetail(
            flag_name="enable_reranker",
            display_name="Cross-Encoder Reranker",
            description="Test",
            category=FlagCategory.RETRIEVAL,
            risk_level=FlagRiskLevel.CACHE_CLEAR,
            enabled=False,
            is_override=True,
            env_default=True,
            updated_at=now,
            updated_by=uid,
        )
        assert detail.is_override is True
        assert detail.updated_by == uid


class TestFeatureFlagListResponse:
    def test_serialization(self):
        resp = FeatureFlagListResponse(items=[])
        assert resp.model_dump() == {"items": []}


class TestFeatureFlagUpdateRequest:
    def test_enabled_true(self):
        req = FeatureFlagUpdateRequest(enabled=True)
        assert req.enabled is True

    def test_enabled_false(self):
        req = FeatureFlagUpdateRequest(enabled=False)
        assert req.enabled is False


class TestFeatureFlagUpdateResponse:
    def test_extends_detail(self):
        resp = FeatureFlagUpdateResponse(
            flag_name="enable_reranker",
            display_name="Cross-Encoder Reranker",
            description="Test",
            category=FlagCategory.RETRIEVAL,
            risk_level=FlagRiskLevel.CACHE_CLEAR,
            enabled=True,
            is_override=True,
            env_default=True,
            caches_cleared=["get_reranker", "get_retriever"],
            restart_required=False,
        )
        assert resp.caches_cleared == ["get_reranker", "get_retriever"]
        assert resp.restart_required is False
