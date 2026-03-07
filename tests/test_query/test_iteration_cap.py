"""Tests for QueryService.build_graph_config recursion limit."""

from types import SimpleNamespace

from app.query.service import QueryService


def test_recursion_limit_standard_tier():
    """Config uses standard limit for generic queries."""
    settings = SimpleNamespace(
        enable_agentic_pipeline=True,
        agentic_recursion_limit_fast=16,
        agentic_recursion_limit_standard=28,
        agentic_recursion_limit_deep=50,
    )

    config = QueryService.build_graph_config("thread-abc", settings, "Tell me about the contract")

    assert config["recursion_limit"] == 28
    assert config["configurable"]["thread_id"] == "thread-abc"


def test_recursion_limit_fast_tier():
    """Config uses fast limit for short factual queries."""
    settings = SimpleNamespace(
        enable_agentic_pipeline=True,
        agentic_recursion_limit_fast=16,
        agentic_recursion_limit_standard=28,
        agentic_recursion_limit_deep=50,
    )

    config = QueryService.build_graph_config("thread-fast", settings, "Who is John Smith?")

    assert config["recursion_limit"] == 16


def test_recursion_limit_deep_tier():
    """Config uses deep limit for complex analytical queries."""
    settings = SimpleNamespace(
        enable_agentic_pipeline=True,
        agentic_recursion_limit_fast=16,
        agentic_recursion_limit_standard=28,
        agentic_recursion_limit_deep=50,
    )

    config = QueryService.build_graph_config(
        "thread-deep", settings, "Compare and contrast the testimony of all witnesses regarding the timeline of events"
    )

    assert config["recursion_limit"] == 50


def test_recursion_limit_no_query_defaults_to_standard():
    """Config defaults to standard limit when no query is provided."""
    settings = SimpleNamespace(
        enable_agentic_pipeline=True,
        agentic_recursion_limit_fast=16,
        agentic_recursion_limit_standard=28,
        agentic_recursion_limit_deep=50,
    )

    config = QueryService.build_graph_config("thread-noq", settings)

    assert config["recursion_limit"] == 28


def test_recursion_limit_absent_when_agentic_disabled():
    """Config omits recursion_limit when agentic pipeline is off."""
    settings = SimpleNamespace(enable_agentic_pipeline=False)

    config = QueryService.build_graph_config("thread-v1", settings, "some query")

    assert "recursion_limit" not in config
    assert config["configurable"]["thread_id"] == "thread-v1"
