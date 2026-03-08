"""Shared helper for logging agent node executions to agent_audit_log.

Used by Case Setup, Entity Resolution, and other LangGraph agent pipelines
to track node-level execution without duplicating audit logic.
"""

from __future__ import annotations

import functools
import time
from collections.abc import Callable
from functools import wraps
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


def log_agent_node(
    agent_id: str,
    node_name: str,
    *,
    postgres_url: str | None = None,
) -> Callable:
    """Decorator that wraps a LangGraph node to log execution to agent_audit_log.

    Works with both sync and async node functions. Uses a standalone DB
    connection (fire-and-forget) so audit failures don't break the pipeline.

    Parameters
    ----------
    agent_id:
        Agent identifier (e.g., ``"case_setup"``, ``"entity_resolution"``).
    node_name:
        Name of the graph node being executed.
    postgres_url:
        Optional Postgres URL. If not provided, falls back to ``get_session_factory``.
    """

    def decorator(fn: Callable) -> Callable:
        import asyncio
        import inspect

        if inspect.iscoroutinefunction(fn):

            @wraps(fn)
            async def async_wrapper(state: dict, *args: Any, **kwargs: Any) -> dict:
                matter_id = state.get("matter_id")
                start = time.perf_counter()
                status = "success"
                error_msg: str | None = None

                try:
                    result = await fn(state, *args, **kwargs)
                    return result
                except Exception as exc:
                    status = "error"
                    error_msg = str(exc)[:200]
                    raise
                finally:
                    duration_ms = round((time.perf_counter() - start) * 1000, 2)
                    # Fire-and-forget audit write
                    try:
                        asyncio.create_task(
                            _write_agent_audit(
                                agent_id=agent_id,
                                node_name=node_name,
                                matter_id=matter_id,
                                duration_ms=duration_ms,
                                status=status,
                                output_summary=error_msg,
                                postgres_url=postgres_url,
                            )
                        )
                    except RuntimeError:
                        # No running event loop (e.g. in sync Celery context)
                        logger.debug(
                            "agent_logging.no_event_loop",
                            agent_id=agent_id,
                            node_name=node_name,
                        )

            return async_wrapper
        else:

            @wraps(fn)
            def sync_wrapper(state: dict, *args: Any, **kwargs: Any) -> dict:
                matter_id = state.get("matter_id")
                start = time.perf_counter()
                status = "success"
                error_msg: str | None = None

                try:
                    result = fn(state, *args, **kwargs)
                    return result
                except Exception as exc:
                    status = "error"
                    error_msg = str(exc)[:200]
                    raise
                finally:
                    duration_ms = round((time.perf_counter() - start) * 1000, 2)
                    _write_agent_audit_sync(
                        agent_id=agent_id,
                        node_name=node_name,
                        matter_id=matter_id,
                        duration_ms=duration_ms,
                        status=status,
                        output_summary=error_msg,
                        postgres_url=postgres_url,
                    )

            return sync_wrapper

    return decorator


async def _write_agent_audit(
    *,
    agent_id: str,
    node_name: str,
    matter_id: str | None,
    duration_ms: float,
    status: str,
    output_summary: str | None = None,
    postgres_url: str | None = None,
) -> None:
    """Write a single agent_audit_log row (async).

    Uses the cached session factory from ``app.dependencies`` to avoid
    creating (and leaking) a new async engine on every call.  The
    ``postgres_url`` parameter is kept for API compatibility but ignored.
    """
    try:
        from sqlalchemy import text as sa_text

        from app.dependencies import get_session_factory

        factory = get_session_factory()
        async with factory() as session:
            await _execute_insert(session, sa_text, agent_id, node_name, matter_id, duration_ms, status, output_summary)
            await session.commit()
    except Exception:
        logger.warning("agent_audit.write_failed", agent_id=agent_id, node_name=node_name, exc_info=True)


@functools.cache
def _get_sync_audit_engine():
    """Return a cached sync SQLAlchemy engine for audit writes."""
    from sqlalchemy import create_engine

    from app.config import Settings

    settings = Settings()
    return create_engine(settings.postgres_url_sync, pool_pre_ping=True)


def _write_agent_audit_sync(
    *,
    agent_id: str,
    node_name: str,
    matter_id: str | None,
    duration_ms: float,
    status: str,
    output_summary: str | None = None,
    postgres_url: str | None = None,
) -> None:
    """Write a single agent_audit_log row (sync — for Celery workers).

    Uses a module-level cached engine via ``_get_sync_audit_engine()`` to
    avoid creating (and leaking) a new engine on every call.  The
    ``postgres_url`` parameter is kept for API compatibility but ignored.
    """
    try:
        from sqlalchemy import text as sa_text

        engine = _get_sync_audit_engine()
        with engine.connect() as conn:
            conn.execute(
                sa_text("""
                    INSERT INTO agent_audit_log
                        (agent_id, action_type, action_name, matter_id,
                         duration_ms, status, output_summary)
                    VALUES
                        (:agent_id, 'node', :node_name,
                         CAST(:matter_id AS UUID),
                         :duration_ms, :status, :output_summary)
                """),
                {
                    "agent_id": agent_id,
                    "node_name": node_name,
                    "matter_id": matter_id,
                    "duration_ms": duration_ms,
                    "status": status,
                    "output_summary": output_summary,
                },
            )
            conn.commit()
    except Exception:
        logger.warning("agent_audit_sync.write_failed", agent_id=agent_id, node_name=node_name, exc_info=True)


async def _execute_insert(
    session: Any,
    sa_text: Any,
    agent_id: str,
    node_name: str,
    matter_id: str | None,
    duration_ms: float,
    status: str,
    output_summary: str | None,
) -> None:
    """Execute the INSERT into agent_audit_log."""
    await session.execute(
        sa_text("""
            INSERT INTO agent_audit_log
                (agent_id, action_type, action_name, matter_id,
                 duration_ms, status, output_summary)
            VALUES
                (:agent_id, 'node', :node_name,
                 CAST(:matter_id AS UUID),
                 :duration_ms, :status, :output_summary)
        """),
        {
            "agent_id": agent_id,
            "node_name": node_name,
            "matter_id": matter_id,
            "duration_ms": duration_ms,
            "status": status,
            "output_summary": output_summary,
        },
    )
