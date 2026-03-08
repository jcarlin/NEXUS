"""Admin-only API endpoints.

GET  /admin/audit-log  -- filterable audit log viewer (admin-only)
GET  /admin/users      -- list users (admin-only)
POST /admin/users      -- create user (admin-only)
PATCH /admin/users/{id} -- update user (admin-only)
DELETE /admin/users/{id} -- deactivate user (admin-only)
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.middleware import require_role
from app.auth.schemas import (
    AuditLogEntry,
    AuditLogListResponse,
    UserCreateRequest,
    UserListResponse,
    UserRecord,
    UserResponse,
    UserUpdateRequest,
)
from app.auth.service import AuthService
from app.dependencies import get_db, get_graph_service
from app.entities.schemas import (
    DocumentEntityStatus,
    KGReprocessRequest,
    KGReprocessResponse,
    KGResolveRequest,
    KGResolveResponse,
    KGStatusResponse,
)

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
    current_user: UserRecord = Depends(require_role("admin")),
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


# ------------------------------------------------------------------
# User CRUD
# ------------------------------------------------------------------


@router.get("/users", response_model=UserListResponse)
async def list_users(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _current_user: UserRecord = Depends(require_role("admin", "attorney")),
) -> UserListResponse:
    """List all users. Admin and attorney roles (attorneys need this for dataset access grants)."""
    count_result = await db.execute(text("SELECT count(*) FROM users"))
    total = count_result.scalar_one()

    result = await db.execute(
        text("""
            SELECT id, email, full_name, role, is_active, created_at
            FROM users
            ORDER BY created_at DESC
            OFFSET :offset LIMIT :limit
        """),
        {"offset": offset, "limit": limit},
    )
    rows = result.mappings().all()
    items = [UserResponse(**dict(r)) for r in rows]
    return UserListResponse(items=items, total=total, offset=offset, limit=limit)


@router.post("/users", response_model=UserResponse, status_code=201)
async def create_user(
    request: UserCreateRequest,
    db: AsyncSession = Depends(get_db),
    _current_user: UserRecord = Depends(require_role("admin")),
) -> UserResponse:
    """Create a new user. Admin-only."""
    existing = await AuthService.get_user_by_email(db, request.email)
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    user = await AuthService.create_user(
        db,
        email=request.email,
        password=request.password,
        full_name=request.full_name,
        role=request.role,
    )
    await db.commit()
    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
    )


@router.patch("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: UUID,
    request: UserUpdateRequest,
    db: AsyncSession = Depends(get_db),
    _current_user: UserRecord = Depends(require_role("admin")),
) -> UserResponse:
    """Update user fields. Admin-only."""
    user = await AuthService.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    set_clauses: list[str] = []
    params: dict = {"user_id": user_id}

    if request.email is not None:
        set_clauses.append("email = :email")
        params["email"] = request.email
    if request.full_name is not None:
        set_clauses.append("full_name = :full_name")
        params["full_name"] = request.full_name
    if request.role is not None:
        set_clauses.append("role = :role")
        params["role"] = request.role
    if request.is_active is not None:
        set_clauses.append("is_active = :is_active")
        params["is_active"] = request.is_active
    if request.password is not None:
        set_clauses.append("password_hash = :password_hash")
        params["password_hash"] = AuthService.hash_password(request.password)

    if not set_clauses:
        raise HTTPException(status_code=400, detail="No fields to update")

    set_clauses.append("updated_at = now()")
    set_sql = ", ".join(set_clauses)

    await db.execute(
        text(f"UPDATE users SET {set_sql} WHERE id = :user_id"),
        params,
    )
    await db.commit()

    updated = await AuthService.get_user_by_id(db, user_id)
    if not updated:
        raise HTTPException(status_code=404, detail="User not found after update")
    return UserResponse(
        id=updated.id,
        email=updated.email,
        full_name=updated.full_name,
        role=updated.role,
        is_active=updated.is_active,
        created_at=updated.created_at,
    )


@router.delete("/users/{user_id}", status_code=204, response_model=None)
async def deactivate_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    _current_user: UserRecord = Depends(require_role("admin")),
):
    """Deactivate a user (soft delete). Admin-only."""
    user = await AuthService.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    await db.execute(
        text("UPDATE users SET is_active = false, updated_at = now() WHERE id = :user_id"),
        {"user_id": user_id},
    )
    await db.commit()


# ------------------------------------------------------------------
# Knowledge Graph Admin
# ------------------------------------------------------------------


@router.get("/knowledge-graph/status", response_model=KGStatusResponse)
async def kg_status(
    db: AsyncSession = Depends(get_db),
    _current_user: UserRecord = Depends(require_role("admin")),
) -> KGStatusResponse:
    """Return knowledge-graph health: node/edge counts + per-document status."""
    gs = get_graph_service()
    stats = await gs.get_graph_stats()

    # Fetch documents with entity counts from Postgres
    result = await db.execute(
        text("""
            SELECT id, filename, entity_count, created_at
            FROM documents
            ORDER BY created_at DESC
            LIMIT 500
        """)
    )
    rows = result.mappings().all()

    # Batch-check which docs have :Document nodes in Neo4j
    doc_ids = [str(r["id"]) for r in rows]
    indexed_ids: set[str] = set()
    if doc_ids:
        try:
            neo4j_result = await gs._run_query(
                "MATCH (d:Document) WHERE d.doc_id IN $ids RETURN d.doc_id AS did",
                {"ids": doc_ids},
            )
            indexed_ids = {r["did"] for r in neo4j_result}
        except Exception:
            pass  # Neo4j might be down

    documents = [
        DocumentEntityStatus(
            doc_id=r["id"],
            filename=r["filename"],
            entity_count=r["entity_count"] or 0,
            neo4j_indexed=str(r["id"]) in indexed_ids,
            created_at=r["created_at"],
        )
        for r in rows
    ]

    return KGStatusResponse(
        total_nodes=stats.get("total_nodes", 0),
        total_edges=stats.get("total_edges", 0),
        node_counts=stats.get("node_counts", {}),
        edge_counts=stats.get("edge_counts", {}),
        documents=documents,
        total_documents=len(documents),
        indexed_documents=len([d for d in documents if d.neo4j_indexed]),
    )


@router.post("/knowledge-graph/reprocess", response_model=KGReprocessResponse)
async def kg_reprocess(
    request: KGReprocessRequest,
    db: AsyncSession = Depends(get_db),
    _current_user: UserRecord = Depends(require_role("admin")),
) -> KGReprocessResponse:
    """Dispatch a Celery task to reprocess documents into Neo4j."""
    from app.entities.tasks import reprocess_entities_to_neo4j

    if request.all_unprocessed:
        # Find docs with entity_count > 0 that aren't in Neo4j
        gs = get_graph_service()
        result = await db.execute(text("SELECT id FROM documents WHERE entity_count > 0"))
        all_ids = [str(r["id"]) for r in result.mappings().all()]

        indexed_ids: set[str] = set()
        if all_ids:
            try:
                neo4j_result = await gs._run_query(
                    "MATCH (d:Document) WHERE d.doc_id IN $ids RETURN d.doc_id AS did",
                    {"ids": all_ids},
                )
                indexed_ids = {r["did"] for r in neo4j_result}
            except Exception:
                pass

        doc_ids = [did for did in all_ids if did not in indexed_ids]
    elif request.document_ids:
        doc_ids = [str(did) for did in request.document_ids]
    else:
        raise HTTPException(status_code=400, detail="Provide document_ids or set all_unprocessed=true")

    if not doc_ids:
        raise HTTPException(status_code=400, detail="No documents to reprocess")

    task = reprocess_entities_to_neo4j.delay(doc_ids)
    return KGReprocessResponse(task_id=task.id, document_count=len(doc_ids))


@router.post("/knowledge-graph/resolve", response_model=KGResolveResponse)
async def kg_resolve(
    request: KGResolveRequest,
    _current_user: UserRecord = Depends(require_role("admin")),
) -> KGResolveResponse:
    """Dispatch entity resolution (simple fuzzy or full agent)."""
    if request.mode == "agent":
        from app.entities.tasks import entity_resolution_agent

        task = entity_resolution_agent.delay(matter_id="00000000-0000-0000-0000-000000000001")
    else:
        from app.entities.tasks import resolve_entities

        task = resolve_entities.delay()

    return KGResolveResponse(task_id=task.id, mode=request.mode)
