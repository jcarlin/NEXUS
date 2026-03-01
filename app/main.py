"""FastAPI application factory and lifespan management for NEXUS."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.common.middleware import AuditLoggingMiddleware, RequestIDMiddleware, RequestLoggingMiddleware, setup_cors
from app.config import Settings
from app.dependencies import (
    close_all,
    get_minio,
    get_neo4j,
    get_qdrant,
    get_redis,
    get_settings,
)

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Structlog configuration (called once at import time)
# ---------------------------------------------------------------------------
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(0),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)


# ---------------------------------------------------------------------------
# Lifespan: startup / shutdown
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Initialise shared resources on startup; tear them down on shutdown."""
    settings: Settings = get_settings()

    logger.info("startup.begin", llm_provider=settings.llm_provider, embedding_provider=settings.embedding_provider)

    # --- Qdrant collections ---
    try:
        qdrant = get_qdrant()
        await qdrant.ensure_collections()
        logger.info("startup.qdrant.ok")
    except Exception as exc:
        logger.error("startup.qdrant.failed", error=str(exc))

    # --- MinIO bucket ---
    try:
        storage = get_minio()
        await storage.ensure_bucket()
        logger.info("startup.minio.ok")
    except Exception as exc:
        logger.error("startup.minio.failed", error=str(exc))

    # --- Neo4j connectivity + schema ---
    try:
        driver = get_neo4j()
        async with driver.session() as session:
            result = await session.run("RETURN 1 AS n")
            await result.consume()
        logger.info("startup.neo4j.ok")

        # Ensure M11 graph schema (constraints + indexes)
        from app.entities.schema import ensure_schema

        await ensure_schema(driver)
        logger.info("startup.neo4j.schema.ok")
    except Exception as exc:
        logger.error("startup.neo4j.failed", error=str(exc))

    # --- Redis ping ---
    try:
        redis = get_redis()
        await redis.ping()
        logger.info("startup.redis.ok")
    except Exception as exc:
        logger.error("startup.redis.failed", error=str(exc))

    # --- LangGraph Checkpointer (PostgresSaver) ---
    try:
        from app.dependencies import get_checkpointer

        get_checkpointer()  # Creates tables if needed (idempotent)
        logger.info("startup.checkpointer.ok")
    except Exception as exc:
        logger.error("startup.checkpointer.failed", error=str(exc))

    # --- PostgreSQL connectivity (via SQLAlchemy engine) ---
    try:
        from sqlalchemy import text as sa_text

        from app.dependencies import _get_engine

        engine = _get_engine()
        async with engine.connect() as conn:
            await conn.execute(sa_text("SELECT 1"))
        logger.info("startup.postgres.ok")
    except Exception as exc:
        logger.error("startup.postgres.failed", error=str(exc))

    logger.info("startup.complete")

    yield  # Application runs here

    # --- Shutdown ---
    logger.info("shutdown.begin")
    await close_all()


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    """Build and return the fully-configured FastAPI application."""
    application = FastAPI(
        title="NEXUS",
        description="Multimodal RAG Investigation Platform for Legal Document Intelligence",
        version="0.1.0",
        lifespan=lifespan,
    )

    # --- Middleware (order matters: outermost first) ---
    setup_cors(application)
    application.add_middleware(RequestLoggingMiddleware)
    application.add_middleware(AuditLoggingMiddleware)
    application.add_middleware(RequestIDMiddleware)

    # --- Domain routers (lazy imports to keep this module lightweight) ---
    from app.analytics.router import router as analytics_router
    from app.annotations.router import router as annotations_router
    from app.audit.router import router as audit_router
    from app.auth.admin_router import router as admin_router
    from app.auth.router import router as auth_router
    from app.cases.router import router as cases_router
    from app.documents.router import router as documents_router
    from app.edrm.router import router as edrm_router
    from app.entities.router import router as entities_router
    from app.evaluation.router import router as evaluation_router
    from app.exports.router import router as exports_router
    from app.ingestion.router import router as ingestion_router
    from app.query.router import router as query_router
    from app.redaction.router import router as redaction_router

    application.include_router(auth_router, prefix="/api/v1")
    application.include_router(ingestion_router, prefix="/api/v1")
    application.include_router(query_router, prefix="/api/v1")
    application.include_router(entities_router, prefix="/api/v1")
    application.include_router(documents_router, prefix="/api/v1")
    application.include_router(admin_router, prefix="/api/v1")
    application.include_router(audit_router, prefix="/api/v1")
    application.include_router(edrm_router, prefix="/api/v1")
    application.include_router(cases_router, prefix="/api/v1")
    application.include_router(analytics_router, prefix="/api/v1")
    application.include_router(annotations_router, prefix="/api/v1")
    application.include_router(exports_router, prefix="/api/v1")
    application.include_router(redaction_router, prefix="/api/v1")
    application.include_router(evaluation_router, prefix="/api/v1")

    # --- Health endpoint ---
    @application.get("/api/v1/health", tags=["system"])
    async def health(request: Request) -> JSONResponse:
        """Ping all five backing services and report their status."""
        status: dict[str, str] = {}

        # Qdrant
        try:
            qdrant = get_qdrant()
            qdrant.client.get_collections()
            status["qdrant"] = "ok"
        except Exception as exc:
            status["qdrant"] = f"error: {exc}"

        # MinIO
        try:
            storage = get_minio()
            await storage.list_objects(prefix="")
            status["minio"] = "ok"
        except Exception as exc:
            status["minio"] = f"error: {exc}"

        # Neo4j
        try:
            driver = get_neo4j()
            async with driver.session() as session:
                result = await session.run("RETURN 1 AS n")
                await result.consume()
            status["neo4j"] = "ok"
        except Exception as exc:
            status["neo4j"] = f"error: {exc}"

        # Redis
        try:
            redis = get_redis()
            await redis.ping()
            status["redis"] = "ok"
        except Exception as exc:
            status["redis"] = f"error: {exc}"

        # PostgreSQL
        try:
            from sqlalchemy import text as sa_text

            from app.dependencies import _get_engine

            engine = _get_engine()
            async with engine.connect() as conn:
                await conn.execute(sa_text("SELECT 1"))
            status["postgres"] = "ok"
        except Exception as exc:
            status["postgres"] = f"error: {exc}"

        all_ok = all(v == "ok" for v in status.values())
        return JSONResponse(
            status_code=200 if all_ok else 503,
            content={"status": "healthy" if all_ok else "degraded", "services": status},
        )

    return application


# Module-level app instance used by ``uvicorn app.main:app``
app = create_app()
