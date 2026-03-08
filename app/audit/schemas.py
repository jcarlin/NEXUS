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


class AgentAuditLogListResponse(PaginatedResponse[AgentAuditLogEntry]):
    """Paginated list of agent audit log entries."""


class AgentSummaryEntry(BaseModel):
    """Aggregate performance metrics for a single agent."""

    agent_id: str
    total_actions: int = 0
    avg_duration_ms: float | None = None
    error_count: int = 0
    tool_call_count: int = 0
    node_count: int = 0
    distinct_tools: int = 0
    first_seen: datetime | None = None
    last_seen: datetime | None = None


class AgentSummaryResponse(BaseModel):
    """Aggregate agent performance metrics."""

    agents: list[AgentSummaryEntry]


class ToolDistributionEntry(BaseModel):
    """Usage count for a single tool."""

    tool_name: str | None = None
    call_count: int = 0


class ToolDistributionResponse(BaseModel):
    """Tool usage distribution across agent runs."""

    tools: list[ToolDistributionEntry]


class RetentionConfig(BaseModel):
    """Audit log retention configuration."""

    retention_days: int = Field(ge=30, description="Minimum 30 days for SOC 2")
    current_count: int = 0
    oldest_entry: datetime | None = None
    entries_beyond_retention: int = 0
