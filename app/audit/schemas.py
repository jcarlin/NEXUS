"""Audit domain Pydantic schemas: AI audit logs, agent audit logs, export, retention."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field

from app.common.models import PaginatedResponse


class ExportFormat(StrEnum):
    CSV = "csv"
    JSON = "json"


class AIAuditLogEntry(BaseModel):
    """Single row from the ai_audit_log table."""

    id: UUID
    request_id: str | None = None
    session_id: UUID | None = None
    user_id: UUID | None = None
    matter_id: UUID | None = None
    call_type: str = "completion"
    node_name: str | None = None
    provider: str
    model: str
    prompt_hash: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    latency_ms: float | None = None
    status: str = "success"
    error_message: str | None = None
    created_at: datetime


class AIAuditLogListResponse(PaginatedResponse[AIAuditLogEntry]):
    """Paginated list of AI audit log entries."""


class AgentAuditLogEntry(BaseModel):
    """Single row from the agent_audit_log table."""

    id: UUID
    session_id: UUID | None = None
    agent_id: str
    request_id: str | None = None
    user_id: UUID | None = None
    matter_id: UUID | None = None
    action_type: str
    action_name: str | None = None
    input_summary: str | None = None
    output_summary: str | None = None
    iteration_number: int | None = None
    duration_ms: float | None = None
    status: str = "success"
    created_at: datetime


class RetentionConfig(BaseModel):
    """Audit log retention configuration."""

    retention_days: int = Field(ge=30, description="Minimum 30 days for SOC 2")
    current_count: int = 0
    oldest_entry: datetime | None = None
    entries_beyond_retention: int = 0
