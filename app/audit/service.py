"""Audit service: request audit logging, AI interaction logging, agent action logging, export, retention."""

from __future__ import annotations

import csv
import io
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = structlog.get_logger(__name__)


class AuditService:
    """Static methods for SOC 2 audit operations. Raw SQL via sqlalchemy.text()."""

    @staticmethod
    async def log_request(
        session_factory: async_sessionmaker[AsyncSession],
        *,
        user_id: UUID | None = None,
        user_email: str | None = None,
        action: str,
        resource: str,
        resource_type: str | None = None,
        matter_id: UUID | None = None,
        ip_address: str,
        user_agent: str | None = None,
        status_code: int,
        duration_ms: float,
        request_id: str | None = None,
        session_id: str | None = None,
    ) -> None:
        """Insert a row into the audit_log table using its own session (fire-and-forget)."""
        async with session_factory() as session:
            await session.execute(
                text("""
                    INSERT INTO audit_log
                        (user_id, user_email, action, resource, resource_type,
                         matter_id, ip_address, user_agent, status_code,
                         duration_ms, request_id, session_id)
                    VALUES
                        (:user_id, :user_email, :action, :resource, :resource_type,
                         :matter_id, :ip_address, :user_agent, :status_code,
                         :duration_ms, :request_id, :session_id)
                """),
                {
                    "user_id": user_id,
                    "user_email": user_email,
                    "action": action,
                    "resource": resource,
                    "resource_type": resource_type,
                    "matter_id": matter_id,
                    "ip_address": ip_address,
                    "user_agent": user_agent,
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                    "request_id": request_id,
                    "session_id": session_id,
                },
            )
            await session.commit()

    @staticmethod
    async def log_ai_call(
        db: AsyncSession,
        *,
        request_id: str | None = None,
        session_id: str | None = None,
        user_id: UUID | None = None,
        matter_id: UUID | None = None,
        call_type: str = "completion",
        node_name: str | None = None,
        provider: str,
        model: str,
        prompt_hash: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        total_tokens: int | None = None,
        latency_ms: float | None = None,
        status: str = "success",
        error_message: str | None = None,
    ) -> None:
        """Insert a row into ai_audit_log."""
        await db.execute(
            text("""
                INSERT INTO ai_audit_log
                    (request_id, session_id, user_id, matter_id, call_type,
                     node_name, provider, model, prompt_hash,
                     input_tokens, output_tokens, total_tokens,
                     latency_ms, status, error_message)
                VALUES
                    (:request_id, :session_id, :user_id, :matter_id, :call_type,
                     :node_name, :provider, :model, :prompt_hash,
                     :input_tokens, :output_tokens, :total_tokens,
                     :latency_ms, :status, :error_message)
            """),
            {
                "request_id": request_id,
                "session_id": session_id,
                "user_id": user_id,
                "matter_id": matter_id,
                "call_type": call_type,
                "node_name": node_name,
                "provider": provider,
                "model": model,
                "prompt_hash": prompt_hash,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "latency_ms": latency_ms,
                "status": status,
                "error_message": error_message,
            },
        )
        await db.commit()

    @staticmethod
    async def log_agent_action(
        db: AsyncSession,
        *,
        session_id: str | None = None,
        agent_id: str,
        request_id: str | None = None,
        user_id: UUID | None = None,
        matter_id: UUID | None = None,
        action_type: str,
        action_name: str | None = None,
        input_summary: str | None = None,
        output_summary: str | None = None,
        iteration_number: int | None = None,
        duration_ms: float | None = None,
        status: str = "success",
    ) -> None:
        """Insert a row into agent_audit_log."""
        await db.execute(
            text("""
                INSERT INTO agent_audit_log
                    (session_id, agent_id, request_id, user_id, matter_id,
                     action_type, action_name, input_summary, output_summary,
                     iteration_number, duration_ms, status)
                VALUES
                    (:session_id, :agent_id, :request_id, :user_id, :matter_id,
                     :action_type, :action_name, :input_summary, :output_summary,
                     :iteration_number, :duration_ms, :status)
            """),
            {
                "session_id": session_id,
                "agent_id": agent_id,
                "request_id": request_id,
                "user_id": user_id,
                "matter_id": matter_id,
                "action_type": action_type,
                "action_name": action_name,
                "input_summary": input_summary,
                "output_summary": output_summary,
                "iteration_number": iteration_number,
                "duration_ms": duration_ms,
                "status": status,
            },
        )
        await db.commit()

    @staticmethod
    async def list_ai_audit_logs(
        db: AsyncSession,
        *,
        session_id: str | None = None,
        node_name: str | None = None,
        provider: str | None = None,
        user_id: UUID | None = None,
        matter_id: UUID | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[dict[str, Any]], int]:
        """Return paginated AI audit log entries with optional filters."""
        where_clauses: list[str] = []
        params: dict[str, Any] = {"offset": offset, "limit": limit}

        if session_id is not None:
            where_clauses.append("session_id = :session_id")
            params["session_id"] = session_id

        if node_name is not None:
            where_clauses.append("node_name = :node_name")
            params["node_name"] = node_name

        if provider is not None:
            where_clauses.append("provider = :provider")
            params["provider"] = provider

        if user_id is not None:
            where_clauses.append("user_id = :user_id")
            params["user_id"] = user_id

        if matter_id is not None:
            where_clauses.append("matter_id = :matter_id")
            params["matter_id"] = matter_id

        if date_from is not None:
            where_clauses.append("created_at >= :date_from")
            params["date_from"] = date_from

        if date_to is not None:
            where_clauses.append("created_at <= :date_to")
            params["date_to"] = date_to

        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        count_result = await db.execute(
            text(f"SELECT count(*) FROM ai_audit_log {where_sql}"),
            params,
        )
        total = count_result.scalar_one()

        result = await db.execute(
            text(f"""
                SELECT id, request_id, session_id, user_id, matter_id,
                       call_type, node_name, provider, model, prompt_hash,
                       input_tokens, output_tokens, total_tokens, latency_ms,
                       status, error_message, created_at
                FROM ai_audit_log
                {where_sql}
                ORDER BY created_at DESC
                OFFSET :offset LIMIT :limit
            """),
            params,
        )
        rows = [dict(r) for r in result.mappings().all()]

        return rows, total

    @staticmethod
    async def export_audit_logs(
        db: AsyncSession,
        *,
        table: str = "ai_audit_log",
        date_from: str | None = None,
        date_to: str | None = None,
        export_format: str = "csv",
    ) -> str:
        """Export audit log entries as CSV or JSON string."""
        if table not in ("ai_audit_log", "agent_audit_log", "audit_log"):
            raise ValueError(f"Invalid table: {table}")

        where_clauses: list[str] = []
        params: dict[str, Any] = {}

        if date_from is not None:
            where_clauses.append("created_at >= :date_from")
            params["date_from"] = date_from

        if date_to is not None:
            where_clauses.append("created_at <= :date_to")
            params["date_to"] = date_to

        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        result = await db.execute(
            text(f"SELECT * FROM {table} {where_sql} ORDER BY created_at DESC"),
            params,
        )
        rows = [dict(r) for r in result.mappings().all()]

        # Serialize UUIDs and datetimes to strings
        for row in rows:
            for key, val in row.items():
                if isinstance(val, UUID):
                    row[key] = str(val)
                elif isinstance(val, datetime):
                    row[key] = val.isoformat()

        if export_format == "json":
            return json.dumps(rows, indent=2)

        # CSV format
        if not rows:
            return ""

        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
        return output.getvalue()

    @staticmethod
    async def get_retention_status(
        db: AsyncSession,
        retention_days: int,
    ) -> dict[str, Any]:
        """Return retention status for the ai_audit_log table."""
        count_result = await db.execute(text("SELECT count(*) FROM ai_audit_log"))
        total = count_result.scalar_one()

        oldest_result = await db.execute(text("SELECT min(created_at) FROM ai_audit_log"))
        oldest = oldest_result.scalar_one()

        cutoff = datetime.now(UTC) - timedelta(days=retention_days)

        beyond_result = await db.execute(
            text("SELECT count(*) FROM ai_audit_log WHERE created_at < :cutoff"),
            {"cutoff": cutoff},
        )
        beyond_count = beyond_result.scalar_one()

        return {
            "retention_days": retention_days,
            "current_count": total,
            "oldest_entry": oldest,
            "entries_beyond_retention": beyond_count,
        }

    @staticmethod
    async def apply_retention(
        db: AsyncSession,
        retention_days: int,
    ) -> int:
        """Return the count of entries that would be archived (older than retention_days).

        Note: Actual deletion requires dropping immutability rules first —
        a privileged DBA operation not exposed via API.
        """
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)

        result = await db.execute(
            text("SELECT count(*) FROM ai_audit_log WHERE created_at < :cutoff"),
            {"cutoff": cutoff},
        )
        return int(result.scalar_one())
