"""Tests for the execution trace infrastructure."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from app.query.trace import (
    TraceStep,
    collect_override_usage,
    emit_tool_trace,
    is_debug_mode,
    reset_override_usage,
    set_debug_mode,
    trace_step,
    track_override_usage,
)


class TestTraceStep:
    """Tests for TraceStep dataclass."""

    def test_to_dict_basic(self):
        step = TraceStep(node="vector_search", label="Searched 23 chunks", duration_ms=340.5)
        d = step.to_dict()
        assert d["node"] == "vector_search"
        assert d["label"] == "Searched 23 chunks"
        assert d["duration_ms"] == 340.5

    def test_to_dict_strips_empty(self):
        step = TraceStep(node="test", label="Test", duration_ms=10.0)
        d = step.to_dict()
        # Empty lists/dicts are falsy and should be stripped
        assert "args_summary" not in d
        assert "result_summary" not in d
        assert "overrides_active" not in d
        assert "tokens" not in d

    def test_to_dict_keeps_populated(self):
        step = TraceStep(
            node="test",
            label="Test",
            duration_ms=10.0,
            args_summary={"top_k": 40},
            result_summary={"chunks": 23},
            overrides_active=["enable_hyde"],
            tokens={"input": 100, "output": 50},
        )
        d = step.to_dict()
        assert d["args_summary"] == {"top_k": 40}
        assert d["result_summary"] == {"chunks": 23}
        assert d["overrides_active"] == ["enable_hyde"]
        assert d["tokens"] == {"input": 100, "output": 50}


class TestOverrideUsageTracking:
    """Tests for contextvar-based override tracking."""

    def test_track_and_collect(self):
        reset_override_usage()
        track_override_usage("enable_hyde")
        track_override_usage("retrieval_text_limit")
        used = collect_override_usage()
        assert used == ["enable_hyde", "retrieval_text_limit"]

    def test_collect_drains(self):
        reset_override_usage()
        track_override_usage("enable_hyde")
        collect_override_usage()
        # Second collect should return empty
        used = collect_override_usage()
        assert used == []

    def test_reset_clears(self):
        reset_override_usage()
        track_override_usage("enable_hyde")
        reset_override_usage()
        used = collect_override_usage()
        assert used == []


class TestDebugMode:
    """Tests for debug mode contextvar."""

    def test_default_off(self):
        set_debug_mode(False)
        assert is_debug_mode() is False

    def test_toggle_on(self):
        set_debug_mode(True)
        assert is_debug_mode() is True
        set_debug_mode(False)  # cleanup


class TestTraceStepDecorator:
    """Tests for @trace_step decorator."""

    @pytest.mark.asyncio
    async def test_passthrough_when_debug_off(self):
        """Function runs normally when debug mode is off."""
        set_debug_mode(False)
        call_count = 0

        @trace_step("Test step")
        async def my_node(state):
            nonlocal call_count
            call_count += 1
            return {"result": "ok"}

        result = await my_node({})
        assert result == {"result": "ok"}
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_captures_timing_when_debug_on(self):
        """Decorator captures timing and emits trace when debug is on."""
        set_debug_mode(True)
        emitted = []

        mock_writer = MagicMock(side_effect=lambda data: emitted.append(data))

        @trace_step("Test node")
        async def my_node(state):
            await asyncio.sleep(0.01)
            return {"done": True}

        with patch("langgraph.config.get_stream_writer", return_value=mock_writer):
            result = await my_node({})

        assert result == {"done": True}
        assert len(emitted) == 1
        trace_data = emitted[0]["trace_step"]
        assert trace_data["node"] == "my_node"
        assert trace_data["label"] == "Test node"
        assert trace_data["duration_ms"] >= 10  # at least 10ms
        set_debug_mode(False)

    @pytest.mark.asyncio
    async def test_captures_override_usage(self):
        """Decorator captures which overrides were used during the step."""
        set_debug_mode(True)
        emitted = []

        mock_writer = MagicMock(side_effect=lambda data: emitted.append(data))

        @trace_step("Step with overrides")
        async def my_node(state):
            track_override_usage("enable_hyde")
            track_override_usage("retrieval_text_limit")
            return {}

        with patch("langgraph.config.get_stream_writer", return_value=mock_writer):
            await my_node({})

        trace_data = emitted[0]["trace_step"]
        assert "enable_hyde" in trace_data["overrides_active"]
        assert "retrieval_text_limit" in trace_data["overrides_active"]
        set_debug_mode(False)


class TestEmitToolTrace:
    """Tests for emit_tool_trace() helper."""

    def test_noop_when_debug_off(self):
        set_debug_mode(False)
        # Should not raise or emit anything
        emit_tool_trace(
            name="vector_search",
            label="Searched docs",
            duration_ms=100.0,
        )

    def test_emits_when_debug_on(self):
        set_debug_mode(True)
        emitted = []
        mock_writer = MagicMock(side_effect=lambda data: emitted.append(data))

        with patch("langgraph.config.get_stream_writer", return_value=mock_writer):
            emit_tool_trace(
                name="vector_search",
                label="Searched 23 chunks",
                duration_ms=340.5,
                args_summary={"top_k": 40, "hyde": True},
                result_summary={"chunks_returned": 23},
            )

        assert len(emitted) == 1
        trace_data = emitted[0]["trace_step"]
        assert trace_data["node"] == "vector_search"
        assert trace_data["kind"] == "tool"
        assert trace_data["args_summary"]["top_k"] == 40
        set_debug_mode(False)


class TestOverrideTrackingInResolvers:
    """Tests that resolve_flag/resolve_param record override usage."""

    def test_resolve_flag_tracks_usage(self):
        from app.query.overrides import resolve_flag

        settings = MagicMock()
        settings.enable_hyde = False
        reset_override_usage()
        resolve_flag("enable_hyde", settings, {"enable_hyde": True})
        used = collect_override_usage()
        assert "enable_hyde" in used

    def test_resolve_flag_no_track_when_same(self):
        from app.query.overrides import resolve_flag

        settings = MagicMock()
        settings.enable_hyde = True
        reset_override_usage()
        resolve_flag("enable_hyde", settings, {"enable_hyde": True})
        used = collect_override_usage()
        assert used == []

    def test_resolve_param_tracks_usage(self):
        from app.query.overrides import resolve_param

        settings = MagicMock()
        settings.retrieval_text_limit = 40
        reset_override_usage()
        resolve_param("retrieval_text_limit", settings, {"retrieval_text_limit": 60})
        used = collect_override_usage()
        assert "retrieval_text_limit" in used

    def test_resolve_param_no_track_when_same(self):
        from app.query.overrides import resolve_param

        settings = MagicMock()
        settings.retrieval_text_limit = 40
        reset_override_usage()
        resolve_param("retrieval_text_limit", settings, {"retrieval_text_limit": 40})
        used = collect_override_usage()
        assert used == []
