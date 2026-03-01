"""Tests for _build_graph_config recursion limit."""

from types import SimpleNamespace

from app.query.router import _build_graph_config


def test_recursion_limit_in_config():
    """Config includes recursion_limit when agentic pipeline is enabled."""
    settings = SimpleNamespace(
        enable_agentic_pipeline=True,
        agentic_recursion_limit_standard=12,
    )

    config = _build_graph_config("thread-abc", settings)

    assert config["recursion_limit"] == 12
    assert config["configurable"]["thread_id"] == "thread-abc"
