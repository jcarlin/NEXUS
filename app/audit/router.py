"""Admin-only audit API endpoints for SOC 2 compliance.

GET  /admin/audit/ai              -- paginated AI interaction audit log
GET  /admin/audit/agents          -- paginated agent audit log
GET  /admin/audit/agents/summary  -- aggregate agent performance metrics
GET  /admin/audit/agents/tools    -- tool usage distribution
GET  /admin/audit/export          -- export audit logs as CSV/JSON
GET  /admin/audit/retention       -- retention status
POST /admin/audit/retention       -- apply retention policy (dry-run)
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.schemas import (
    AIAuditLogEntry,
    AIAuditLogListResponse,
    AgentAuditLogEntry,
    AgentAuditLogListResponse,
    AgentSummaryEntry,
    AgentSummaryResponse,
    RetentionConfig,
    ToolDistributionEntry,
    ToolDistributionResponse,
)
from app.audit.service import AuditService
from app.auth.middleware import require_role
from app.auth.schemas import UserRecord
from app.dependencies import get_db, get_settings

router = APIRouter(prefix="/admin/audit", tags=["admin", "audit"])


@router.get("/ai", response_model=AIAuditLogListResponse)
async def list_ai_audit_logs(
    session_id: str | None = Query(None, description="Filter by session ID"),
    node_name: str | None = Query(None, description="Filter by graph node name"),
    provider: str | None = Query(None, description="Filter by LLM provider"),
    date_from: str | None = Query(None, description="ISO datetime lower bound"),
    date_to: str | None = Query(None, description="ISO datetime upper bound"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(require_role("admin")),
) -> AIAuditLogListResponse:
    """Return a paginated, filterable AI audit log. Admin-only."""
    rows, total = await AuditService.list_ai_audit_logs(
        db,
        session_id=session_id,
        node_name=node_name,
        provider=provider,
        date_from=date_from,
        date_to=date_to,
        offset=offset,
        limit=limit,
    )
    items = [AIAuditLogEntry(**r) for r in rows]
    return AIAuditLogListResponse(items=items, total=total, offset=offset, limit=limit)


@router.get("/agents", response_model=AgentAuditLogListResponse)
async def list_agent_audit_logs(
    agent_id: str | None = Query(None, description="Filter by agent ID (e.g. investigation_agent, case_setup)"),
    matter_id: UUID | None = Query(None, description="Filter by matter ID"),
    action_type: str | None = Query(None, description="Filter by action type (tool_call, tool_result, node)"),
    request_id: str | None = Query(None, description="Filter by request ID"),
    date_from: str | None = Query(None, description="ISO datetime lower bound"),
    date_to: str | None = Query(None, description="ISO datetime upper bound"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(require_role("admin")),
) -> AgentAuditLogListResponse:
    """Return a paginated, filterable agent audit log. Admin-only."""
    rows, total = await AuditService.list_agent_audit_logs(
        db,
        agent_id=agent_id,
        matter_id=matter_id,
        action_type=action_type,
        request_id=request_id,
        date_from=date_from,
        date_to=date_to,
        offset=offset,
        limit=limit,
    )
    items = [AgentAuditLogEntry(**r) for r in rows]
    return AgentAuditLogListResponse(items=items, total=total, offset=offset, limit=limit)


@router.get("/agents/summary", response_model=AgentSummaryResponse)
async def get_agent_summary(
    matter_id: UUID | None = Query(None, description="Filter by matter ID"),
    date_from: str | None = Query(None, description="ISO datetime lower bound"),
    date_to: str | None = Query(None, description="ISO datetime upper bound"),
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(require_role("admin")),
) -> AgentSummaryResponse:
    """Return aggregate performance metrics per agent. Admin-only."""
    rows = await AuditService.get_agent_summary(
        db,
        matter_id=matter_id,
        date_from=date_from,
        date_to=date_to,
    )
    agents = [AgentSummaryEntry(**r) for r in rows]
    return AgentSummaryResponse(agents=agents)


@router.get("/agents/tools", response_model=ToolDistributionResponse)
async def get_tool_distribution(
    agent_id: str | None = Query(None, description="Filter by agent ID"),
    matter_id: UUID | None = Query(None, description="Filter by matter ID"),
    date_from: str | None = Query(None, description="ISO datetime lower bound"),
    date_to: str | None = Query(None, description="ISO datetime upper bound"),
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(require_role("admin")),
) -> ToolDistributionResponse:
    """Return tool usage distribution across agent runs. Admin-only."""
    rows = await AuditService.get_tool_distribution(
        db,
        agent_id=agent_id,
        matter_id=matter_id,
        date_from=date_from,
        date_to=date_to,
    )
    tools = [ToolDistributionEntry(**r) for r in rows]
    return ToolDistributionResponse(tools=tools)


@router.get("/export")
async def export_audit_logs(
    table: str = Query("ai_audit_log", description="Table to export"),
    format: str = Query("csv", description="Export format: csv or json"),
    date_from: str | None = Query(None, description="ISO datetime lower bound"),
    date_to: str | None = Query(None, description="ISO datetime upper bound"),
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(require_role("admin")),
) -> PlainTextResponse:
    """Export audit log entries as CSV or JSON. Admin-only."""
    content = await AuditService.export_audit_logs(
        db,
        table=table,
        date_from=date_from,
        date_to=date_to,
        export_format=format,
    )
    media_type = "application/json" if format == "json" else "text/csv"
    filename = f"{table}_export.{format}"
    return PlainTextResponse(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/retention", response_model=RetentionConfig)
async def get_retention_status(
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(require_role("admin")),
) -> RetentionConfig:
    """Return retention status for the AI audit log. Admin-only."""
    settings = get_settings()
    status = await AuditService.get_retention_status(db, settings.audit_retention_days)
    return RetentionConfig(**status)


@router.post("/retention", response_model=dict)
async def apply_retention(
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(require_role("admin")),
) -> dict:
    """Dry-run retention policy: returns count of entries that would be archived. Admin-only."""
    settings = get_settings()
    count = await AuditService.apply_retention(db, settings.audit_retention_days)
    return {
        "retention_days": settings.audit_retention_days,
        "entries_to_archive": count,
        "dry_run": True,
    }
