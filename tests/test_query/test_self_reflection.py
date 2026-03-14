"""Tests for T2-8: Self-reflection loop."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.query.graph import _route_after_verification
from app.query.nodes import reflect


class TestRouteAfterVerification:
    """Test the conditional edge routing after verify_citations."""

    def test_routes_to_end_when_disabled(self):
        """Feature flag off -> always END."""
        state = {
            "cited_claims": [
                {"verification_status": "flagged", "claim_text": "bad claim"},
            ],
            "_reflection_count": 0,
        }
        with patch("app.dependencies.get_settings") as mock_settings:
            mock_settings.return_value.enable_self_reflection = False
            result = _route_after_verification(state)
        assert result == "end"

    def test_routes_to_end_when_no_claims(self):
        """No claims -> END."""
        state = {"cited_claims": [], "_reflection_count": 0}
        with patch("app.dependencies.get_settings") as mock_settings:
            mock_settings.return_value.enable_self_reflection = True
            result = _route_after_verification(state)
        assert result == "end"

    def test_routes_to_end_when_faithfulness_above_threshold(self):
        """All verified -> faithfulness 1.0 >= 0.8 -> END."""
        state = {
            "cited_claims": [
                {"verification_status": "verified"},
                {"verification_status": "verified"},
                {"verification_status": "verified"},
            ],
            "_reflection_count": 0,
        }
        with patch("app.dependencies.get_settings") as mock_settings:
            mock_settings.return_value.enable_self_reflection = True
            mock_settings.return_value.self_reflection_faithfulness_threshold = 0.8
            mock_settings.return_value.self_reflection_max_retries = 1
            mock_settings.return_value.self_reflection_min_claims = 3
            result = _route_after_verification(state)
        assert result == "end"

    def test_routes_to_reflect_when_below_threshold(self):
        """1/3 verified = 0.33 < 0.8 -> reflect."""
        state = {
            "cited_claims": [
                {"verification_status": "verified"},
                {"verification_status": "flagged"},
                {"verification_status": "flagged"},
            ],
            "_reflection_count": 0,
        }
        with patch("app.dependencies.get_settings") as mock_settings:
            mock_settings.return_value.enable_self_reflection = True
            mock_settings.return_value.self_reflection_faithfulness_threshold = 0.8
            mock_settings.return_value.self_reflection_max_retries = 1
            mock_settings.return_value.self_reflection_min_claims = 3
            result = _route_after_verification(state)
        assert result == "reflect"

    def test_routes_to_end_when_retries_exhausted(self):
        """Below threshold but retries exhausted -> END."""
        state = {
            "cited_claims": [
                {"verification_status": "flagged"},
                {"verification_status": "flagged"},
                {"verification_status": "flagged"},
            ],
            "_reflection_count": 1,
        }
        with patch("app.dependencies.get_settings") as mock_settings:
            mock_settings.return_value.enable_self_reflection = True
            mock_settings.return_value.self_reflection_faithfulness_threshold = 0.8
            mock_settings.return_value.self_reflection_max_retries = 1
            mock_settings.return_value.self_reflection_min_claims = 3
            result = _route_after_verification(state)
        assert result == "end"

    def test_exact_threshold_routes_to_end(self):
        """Faithfulness == threshold -> END (>= comparison)."""
        state = {
            "cited_claims": [
                {"verification_status": "verified"},
                {"verification_status": "verified"},
                {"verification_status": "verified"},
                {"verification_status": "verified"},
                {"verification_status": "flagged"},
            ],
            "_reflection_count": 0,
        }
        with patch("app.dependencies.get_settings") as mock_settings:
            mock_settings.return_value.enable_self_reflection = True
            mock_settings.return_value.self_reflection_faithfulness_threshold = 0.8
            mock_settings.return_value.self_reflection_max_retries = 1
            mock_settings.return_value.self_reflection_min_claims = 3
            result = _route_after_verification(state)
        assert result == "end"

    def test_zero_verified_routes_to_reflect(self):
        """0/3 verified = faithfulness 0.0 < 0.8 -> reflect."""
        state = {
            "cited_claims": [
                {"verification_status": "flagged"},
                {"verification_status": "flagged"},
                {"verification_status": "flagged"},
            ],
            "_reflection_count": 0,
        }
        with patch("app.dependencies.get_settings") as mock_settings:
            mock_settings.return_value.enable_self_reflection = True
            mock_settings.return_value.self_reflection_faithfulness_threshold = 0.8
            mock_settings.return_value.self_reflection_max_retries = 1
            mock_settings.return_value.self_reflection_min_claims = 3
            result = _route_after_verification(state)
        assert result == "reflect"

    def test_routes_to_end_when_below_min_claims(self):
        """Too few claims to judge reliably -> END (skip reflection)."""
        state = {
            "cited_claims": [
                {"verification_status": "flagged"},
            ],
            "_reflection_count": 0,
        }
        with patch("app.dependencies.get_settings") as mock_settings:
            mock_settings.return_value.enable_self_reflection = True
            mock_settings.return_value.self_reflection_faithfulness_threshold = 0.8
            mock_settings.return_value.self_reflection_max_retries = 1
            mock_settings.return_value.self_reflection_min_claims = 3
            result = _route_after_verification(state)
        assert result == "end"


class TestReflectNode:
    """Test the reflect node function."""

    @pytest.mark.asyncio
    async def test_appends_human_message(self):
        """Verify reflect appends a HumanMessage with flagged claims."""
        from langchain_core.messages import HumanMessage

        state = {
            "cited_claims": [
                {"claim_text": "Claim A was true", "verification_status": "flagged"},
                {"claim_text": "Claim B was false", "verification_status": "verified"},
                {"claim_text": "Claim C is unsupported", "verification_status": "flagged"},
            ],
            "_reflection_count": 0,
        }

        result = await reflect(state)

        assert "messages" in result
        assert len(result["messages"]) == 1
        msg = result["messages"][0]
        assert isinstance(msg, HumanMessage)
        assert "Claim A was true" in msg.content
        assert "Claim C is unsupported" in msg.content
        # Verified claims should NOT be in the message
        assert "Claim B was false" not in msg.content

    @pytest.mark.asyncio
    async def test_increments_reflection_count(self):
        """Verify _reflection_count is incremented."""
        state = {
            "cited_claims": [
                {"claim_text": "flagged", "verification_status": "flagged"},
            ],
            "_reflection_count": 0,
        }

        result = await reflect(state)
        assert result["_reflection_count"] == 1

    @pytest.mark.asyncio
    async def test_increments_from_existing_count(self):
        """Verify _reflection_count increments from existing value."""
        state = {
            "cited_claims": [
                {"claim_text": "flagged", "verification_status": "flagged"},
            ],
            "_reflection_count": 2,
        }

        result = await reflect(state)
        assert result["_reflection_count"] == 3

    @pytest.mark.asyncio
    async def test_stores_flagged_claims(self):
        """Verify _flagged_claims is populated with flagged claims."""
        flagged_claim = {"claim_text": "flagged one", "verification_status": "flagged"}
        state = {
            "cited_claims": [
                flagged_claim,
                {"claim_text": "verified one", "verification_status": "verified"},
            ],
            "_reflection_count": 0,
        }

        result = await reflect(state)
        assert len(result["_flagged_claims"]) == 1
        assert result["_flagged_claims"][0]["claim_text"] == "flagged one"

    @pytest.mark.asyncio
    async def test_empty_claims_produces_empty_message(self):
        """Verify reflect handles empty cited_claims gracefully."""
        state = {
            "cited_claims": [],
            "_reflection_count": 0,
        }

        result = await reflect(state)
        assert result["_reflection_count"] == 1
        assert result["_flagged_claims"] == []
        assert len(result["messages"]) == 1
