"""Execution trace infrastructure for the dev trace panel.

Captures per-step timing, tool arguments, result summaries, and
override impact annotations.  Trace data is emitted via LangGraph's
custom stream writer and forwarded as SSE events when ``debug=True``.

The contextvar-based override tracking is zero-cost when not in debug
mode — ``resolve_flag`` / ``resolve_param`` only call ``track_override_usage``
when overrides are actually applied.
"""

from __future__ import annotations

import time
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from functools import wraps
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# TraceStep data structure
# ---------------------------------------------------------------------------


@dataclass
class TraceStep:
    """A single execution step in the query pipeline trace."""

    node: str
    label: str
    duration_ms: float = 0.0
    args_summary: dict[str, Any] = field(default_factory=dict)
    result_summary: dict[str, Any] = field(default_factory=dict)
    overrides_active: list[str] = field(default_factory=list)
    tokens: dict[str, int] | None = None  # {"input": N, "output": N}
    kind: str = "step"  # "step" | "tool" | "llm"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # Strip empty fields to keep SSE payloads small
        return {k: v for k, v in d.items() if v}


# ---------------------------------------------------------------------------
# Override usage tracking via contextvars
# ---------------------------------------------------------------------------

_override_usage: ContextVar[list[str]] = ContextVar("_override_usage", default=[])
_debug_mode: ContextVar[bool] = ContextVar("_debug_mode", default=False)


def set_debug_mode(enabled: bool) -> None:
    """Set whether debug tracing is active for the current async context."""
    _debug_mode.set(enabled)


def is_debug_mode() -> bool:
    """Check if debug tracing is active."""
    return _debug_mode.get()


def track_override_usage(name: str) -> None:
    """Record that an override was applied for the current step.

    Called by ``resolve_flag`` / ``resolve_param`` when a per-request
    override is actually used (differs from global default).
    """
    try:
        _override_usage.get().append(name)
    except LookupError:
        pass


def collect_override_usage() -> list[str]:
    """Drain accumulated override usage for the current step."""
    try:
        used = _override_usage.get()
        _override_usage.set([])
        return used
    except LookupError:
        return []


def reset_override_usage() -> None:
    """Reset override usage tracking for the next step."""
    _override_usage.set([])


# ---------------------------------------------------------------------------
# @trace_step decorator for graph nodes
# ---------------------------------------------------------------------------


def trace_step(label: str, kind: str = "step"):
    """Decorator that captures timing and override usage for a graph node.

    Emits a ``trace_step`` event via LangGraph's ``get_stream_writer()``
    when debug mode is active.
    """

    def decorator(fn):
        @wraps(fn)
        async def wrapper(*args, **kwargs):
            if not is_debug_mode():
                return await fn(*args, **kwargs)

            reset_override_usage()
            t0 = time.perf_counter()
            result = await fn(*args, **kwargs)
            duration_ms = round((time.perf_counter() - t0) * 1000, 1)
            overrides_used = collect_override_usage()

            step = TraceStep(
                node=fn.__name__,
                label=label,
                duration_ms=duration_ms,
                overrides_active=overrides_used,
                kind=kind,
            )

            try:
                from langgraph.config import get_stream_writer

                writer = get_stream_writer()
                writer({"trace_step": step.to_dict()})
            except Exception:
                # Outside streaming context or writer unavailable
                pass

            return result

        return wrapper

    return decorator


def emit_tool_trace(
    name: str,
    label: str,
    duration_ms: float,
    args_summary: dict[str, Any] | None = None,
    result_summary: dict[str, Any] | None = None,
    overrides: list[str] | None = None,
) -> None:
    """Emit a trace step for an agent tool call.

    Called inline from tool functions (not via decorator, since tools
    have their own parameter extraction logic).
    """
    if not is_debug_mode():
        return

    step = TraceStep(
        node=name,
        label=label,
        duration_ms=duration_ms,
        args_summary=args_summary or {},
        result_summary=result_summary or {},
        overrides_active=overrides or collect_override_usage(),
        kind="tool",
    )

    try:
        from langgraph.config import get_stream_writer

        writer = get_stream_writer()
        writer({"trace_step": step.to_dict()})
    except Exception:
        pass
