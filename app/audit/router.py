"""Admin-only audit API endpoints for SOC 2 compliance.

GET  /admin/audit/ai         -- paginated AI interaction audit log
GET  /admin/audit/export     -- export audit logs as CSV/JSON
GET  /admin/audit/retention  -- retention status
POST /admin/audit/retention  -- apply retention policy (dry-run)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.schemas import AIAuditLogEntry, AIAuditLogListResponse, RetentionConfig
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
