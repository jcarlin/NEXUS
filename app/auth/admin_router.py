"""Admin-only API endpoints.

GET /admin/audit-log  -- filterable audit log viewer (admin-only)
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.middleware import require_role
from app.auth.schemas import AuditLogEntry, AuditLogListResponse
from app.dependencies import get_db

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/audit-log", response_model=AuditLogListResponse)
async def list_audit_log(
    user_id: UUID | None = Query(None, description="Filter by user"),
    action: str | None = Query(None, description="Filter by HTTP method"),
    resource_type: str | None = Query(None, description="Filter by resource type"),
    matter_id: UUID | None = Query(None, description="Filter by matter"),
    status_code: int | None = Query(None, description="Filter by status code"),
    date_from: str | None = Query(None, description="ISO datetime lower bound"),
    date_to: str | None = Query(None, description="ISO datetime upper bound"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_role("admin")),
):
    """Return a paginated, filterable audit log. Admin-only."""
    where_clauses: list[str] = []
    params: dict = {"offset": offset, "limit": limit}

    if user_id is not None:
        where_clauses.append("user_id = :user_id")
        params["user_id"] = user_id

    if action is not None:
        where_clauses.append("action = :action")
        params["action"] = action

    if resource_type is not None:
        where_clauses.append("resource_type = :resource_type")
        params["resource_type"] = resource_type

    if matter_id is not None:
        where_clauses.append("matter_id = :matter_id")
        params["matter_id"] = matter_id

    if status_code is not None:
        where_clauses.append("status_code = :status_code")
        params["status_code"] = status_code

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
        text(f"SELECT count(*) FROM audit_log {where_sql}"),
        params,
    )
    total = count_result.scalar_one()

    result = await db.execute(
        text(f"""
            SELECT id, user_id, user_email, action, resource, resource_type,
                   matter_id, ip_address, user_agent, status_code,
                   duration_ms, request_id, created_at
            FROM audit_log
            {where_sql}
            ORDER BY created_at DESC
            OFFSET :offset LIMIT :limit
        """),
        params,
    )
    rows = result.mappings().all()

    items = [AuditLogEntry(**dict(r)) for r in rows]

    return AuditLogListResponse(
        items=items,
        total=total,
        offset=offset,
        limit=limit,
    )
