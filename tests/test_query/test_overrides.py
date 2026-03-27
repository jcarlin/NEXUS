"""Tests for per-request retrieval strategy override resolution."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.query.overrides import (
    OVERRIDABLE_FLAGS,
    OVERRIDABLE_PARAMS,
    OverrideCategory,
    get_override_category,
    resolve_flag,
    resolve_param,
    validate_overrides,
)


def _make_settings(**kwargs) -> MagicMock:
    """Create a mock Settings with the given flag and param values."""
    settings = MagicMock()
    defaults = {
        # Boolean flags
        "enable_hyde": False,
        "enable_multi_query_expansion": False,
        "enable_retrieval_grading": False,
        "enable_citation_verification": True,
        "enable_self_reflection": False,
        "enable_text_to_cypher": False,
        "enable_text_to_sql": False,
        "enable_question_decomposition": False,
        "enable_prompt_routing": False,
        "enable_adaptive_retrieval_depth": False,
        "enable_reranker": True,
        "enable_sparse_embeddings": False,
        "enable_visual_embeddings": False,
        # Numeric params
        "retrieval_text_limit": 40,
        "retrieval_graph_limit": 20,
        "multi_query_count": 3,
        "hyde_blend_ratio": 0.5,
        "reranker_top_n": 10,
        "query_entity_threshold": 0.5,
        "self_reflection_faithfulness_threshold": 0.6,
    }
    defaults.update(kwargs)
    for k, v in defaults.items():
        setattr(settings, k, v)
    return settings


class TestResolveFlag:
    """Tests for resolve_flag()."""

    def test_no_overrides_returns_global(self):
        settings = _make_settings(enable_hyde=False)
        assert resolve_flag("enable_hyde", settings, None) is False

    def test_no_overrides_returns_global_true(self):
        settings = _make_settings(enable_reranker=True)
        assert resolve_flag("enable_reranker", settings, None) is True

    def test_empty_overrides_returns_global(self):
        settings = _make_settings(enable_hyde=False)
        assert resolve_flag("enable_hyde", settings, {}) is False

    def test_flag_not_in_overrides_returns_global(self):
        settings = _make_settings(enable_hyde=False)
        assert resolve_flag("enable_hyde", settings, {"enable_reranker": False}) is False

    def test_logic_flag_enable(self):
        """Logic-branch flag can be freely enabled."""
        settings = _make_settings(enable_hyde=False)
        assert resolve_flag("enable_hyde", settings, {"enable_hyde": True}) is True

    def test_logic_flag_disable(self):
        """Logic-branch flag can be freely disabled."""
        settings = _make_settings(enable_citation_verification=True)
        assert resolve_flag("enable_citation_verification", settings, {"enable_citation_verification": False}) is False

    def test_di_gated_disable_when_globally_on(self):
        """DI-gated flag can be disabled when globally enabled."""
        settings = _make_settings(enable_reranker=True)
        assert resolve_flag("enable_reranker", settings, {"enable_reranker": False}) is False

    def test_di_gated_enable_blocked_when_globally_off(self):
        """DI-gated flag cannot be enabled when globally off (model not loaded)."""
        settings = _make_settings(enable_reranker=False)
        assert resolve_flag("enable_reranker", settings, {"enable_reranker": True}) is False

    def test_di_gated_enable_allowed_when_globally_on(self):
        """DI-gated flag can stay enabled when globally on (no-op override)."""
        settings = _make_settings(enable_reranker=True)
        assert resolve_flag("enable_reranker", settings, {"enable_reranker": True}) is True

    def test_sparse_embeddings_di_gated(self):
        settings = _make_settings(enable_sparse_embeddings=False)
        assert resolve_flag("enable_sparse_embeddings", settings, {"enable_sparse_embeddings": True}) is False

    def test_visual_embeddings_di_gated(self):
        settings = _make_settings(enable_visual_embeddings=False)
        assert resolve_flag("enable_visual_embeddings", settings, {"enable_visual_embeddings": True}) is False


class TestValidateOverrides:
    """Tests for validate_overrides()."""

    def test_none_returns_empty(self):
        settings = _make_settings()
        assert validate_overrides(None, settings) == {}

    def test_empty_returns_empty(self):
        settings = _make_settings()
        assert validate_overrides({}, settings) == {}

    def test_strips_none_values(self):
        settings = _make_settings()
        result = validate_overrides({"enable_hyde": None, "enable_reranker": False}, settings)
        assert result == {"enable_reranker": False}

    def test_rejects_unknown_flags(self):
        settings = _make_settings()
        result = validate_overrides({"enable_unknown_flag": True, "enable_hyde": True}, settings)
        assert result == {"enable_hyde": True}
        assert "enable_unknown_flag" not in result

    def test_applies_di_gate(self):
        """DI-gated flag enable rejected when globally off."""
        settings = _make_settings(enable_reranker=False)
        result = validate_overrides({"enable_reranker": True}, settings)
        assert result == {}

    def test_di_gate_allows_disable(self):
        """DI-gated flag disable allowed when globally on."""
        settings = _make_settings(enable_reranker=True)
        result = validate_overrides({"enable_reranker": False}, settings)
        assert result == {"enable_reranker": False}

    def test_multiple_flags(self):
        settings = _make_settings(enable_reranker=True)
        result = validate_overrides(
            {
                "enable_hyde": True,
                "enable_reranker": False,
                "enable_citation_verification": False,
            },
            settings,
        )
        assert result == {
            "enable_hyde": True,
            "enable_reranker": False,
            "enable_citation_verification": False,
        }


class TestOverrideCategory:
    """Tests for get_override_category()."""

    def test_logic_flags(self):
        assert get_override_category("enable_hyde") == OverrideCategory.LOGIC
        assert get_override_category("enable_citation_verification") == OverrideCategory.LOGIC

    def test_di_gated_flags(self):
        assert get_override_category("enable_reranker") == OverrideCategory.DI_GATED
        assert get_override_category("enable_sparse_embeddings") == OverrideCategory.DI_GATED
        assert get_override_category("enable_visual_embeddings") == OverrideCategory.DI_GATED


class TestOverridableFlags:
    """Tests for OVERRIDABLE_FLAGS constant."""

    def test_contains_expected_flags(self):
        assert "enable_hyde" in OVERRIDABLE_FLAGS
        assert "enable_reranker" in OVERRIDABLE_FLAGS
        assert "enable_citation_verification" in OVERRIDABLE_FLAGS

    def test_excludes_non_overridable(self):
        assert "enable_agentic_pipeline" not in OVERRIDABLE_FLAGS
        assert "enable_case_setup_agent" not in OVERRIDABLE_FLAGS
        assert "enable_agent_clarification" not in OVERRIDABLE_FLAGS

    @pytest.mark.parametrize("flag", sorted(OVERRIDABLE_FLAGS))
    def test_all_flags_have_labels(self, flag: str):
        from app.query.overrides import OVERRIDE_LABELS

        assert flag in OVERRIDE_LABELS, f"{flag} missing from OVERRIDE_LABELS"

    @pytest.mark.parametrize("flag", sorted(OVERRIDABLE_FLAGS))
    def test_all_flags_have_descriptions(self, flag: str):
        from app.query.overrides import OVERRIDE_DESCRIPTIONS

        assert flag in OVERRIDE_DESCRIPTIONS, f"{flag} missing from OVERRIDE_DESCRIPTIONS"


class TestResolveParam:
    """Tests for resolve_param()."""

    def test_no_overrides_returns_global(self):
        settings = _make_settings(retrieval_text_limit=40)
        assert resolve_param("retrieval_text_limit", settings, None) == 40

    def test_empty_overrides_returns_global(self):
        settings = _make_settings(hyde_blend_ratio=0.5)
        assert resolve_param("hyde_blend_ratio", settings, {}) == 0.5

    def test_override_int(self):
        settings = _make_settings(retrieval_text_limit=40)
        assert resolve_param("retrieval_text_limit", settings, {"retrieval_text_limit": 60}) == 60

    def test_override_float(self):
        settings = _make_settings(hyde_blend_ratio=0.5)
        assert resolve_param("hyde_blend_ratio", settings, {"hyde_blend_ratio": 0.8}) == 0.8

    def test_param_not_in_overrides_returns_global(self):
        settings = _make_settings(reranker_top_n=10)
        assert resolve_param("reranker_top_n", settings, {"retrieval_text_limit": 60}) == 10


class TestValidateOverridesNumeric:
    """Tests for validate_overrides() with numeric parameters."""

    def test_numeric_param_accepted(self):
        settings = _make_settings()
        result = validate_overrides({"retrieval_text_limit": 60}, settings)
        assert result == {"retrieval_text_limit": 60}

    def test_numeric_float_param_accepted(self):
        settings = _make_settings()
        result = validate_overrides({"hyde_blend_ratio": 0.8}, settings)
        assert result == {"hyde_blend_ratio": 0.8}

    def test_numeric_clamped_to_max(self):
        settings = _make_settings()
        result = validate_overrides({"retrieval_text_limit": 200}, settings)
        assert result["retrieval_text_limit"] == 100  # max is 100

    def test_numeric_clamped_to_min(self):
        settings = _make_settings()
        result = validate_overrides({"retrieval_text_limit": 1}, settings)
        assert result["retrieval_text_limit"] == 5  # min is 5

    def test_float_clamped_to_range(self):
        settings = _make_settings()
        result = validate_overrides({"hyde_blend_ratio": 1.5}, settings)
        assert result["hyde_blend_ratio"] == 1.0

    def test_mixed_bool_and_numeric(self):
        settings = _make_settings(enable_reranker=True)
        result = validate_overrides(
            {
                "enable_hyde": True,
                "retrieval_text_limit": 60,
                "reranker_top_n": 20,
            },
            settings,
        )
        assert result == {
            "enable_hyde": True,
            "retrieval_text_limit": 60,
            "reranker_top_n": 20,
        }

    def test_rejects_non_numeric_for_param(self):
        settings = _make_settings()
        result = validate_overrides({"retrieval_text_limit": "sixty"}, settings)
        assert "retrieval_text_limit" not in result

    def test_rejects_unknown_param(self):
        settings = _make_settings()
        result = validate_overrides({"unknown_param": 42}, settings)
        assert result == {}

    def test_int_param_cast(self):
        """Float values for int params are cast to int."""
        settings = _make_settings()
        result = validate_overrides({"retrieval_text_limit": 60.7}, settings)
        assert result["retrieval_text_limit"] == 60
        assert isinstance(result["retrieval_text_limit"], int)


class TestOverridableParams:
    """Tests for OVERRIDABLE_PARAMS constant."""

    def test_contains_expected_params(self):
        assert "retrieval_text_limit" in OVERRIDABLE_PARAMS
        assert "hyde_blend_ratio" in OVERRIDABLE_PARAMS
        assert "reranker_top_n" in OVERRIDABLE_PARAMS

    def test_param_meta_fields(self):
        meta = OVERRIDABLE_PARAMS["retrieval_text_limit"]
        assert meta.display_name
        assert meta.description
        assert meta.param_type == "int"
        assert meta.min_value == 5
        assert meta.max_value == 100

    def test_all_params_have_valid_type(self):
        for name, meta in OVERRIDABLE_PARAMS.items():
            assert meta.param_type in ("int", "float"), f"{name} has invalid param_type"
