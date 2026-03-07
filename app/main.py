"""FastAPI application factory and lifespan management for NEXUS."""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.auth.middleware import get_current_user
from app.common.middleware import AuditLoggingMiddleware, RequestIDMiddleware, RequestLoggingMiddleware, setup_cors
from app.config import Settings
from app.dependencies import (
    close_all,
    get_embedder,
    get_llm,
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
_log_level_int = getattr(logging, get_settings().log_level.upper(), logging.INFO)
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(_log_level_int),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

# ---------------------------------------------------------------------------
# Silence noisy third-party loggers (stdlib logging, not structlog)
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
for _noisy_logger in (
    "httpx",
    "httpcore",
    "transformers",
    "huggingface_hub",
    "sentence_transformers",
    "sentencepiece",
    "qdrant_client",
    "neo4j",
    "urllib3",
    "multipart",
    "asyncio",
):
    logging.getLogger(_noisy_logger).setLevel(logging.ERROR)


# ---------------------------------------------------------------------------
# Lifespan: startup / shutdown
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Initialise shared resources on startup; tear them down on shutdown."""
    settings: Settings = get_settings()

    # --- LangSmith tracing (env vars consumed by LangGraph / ChatAnthropic) ---
    if settings.langchain_tracing_v2 and settings.langchain_api_key:
        os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
        os.environ.setdefault("LANGCHAIN_API_KEY", settings.langchain_api_key)
        os.environ.setdefault("LANGCHAIN_PROJECT", settings.langchain_project)
        logger.info("startup.langsmith.enabled", project=settings.langchain_project)
    else:
        logger.info("startup.langsmith.disabled")

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
    from app.datasets.router import router as datasets_router
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
    application.include_router(datasets_router, prefix="/api/v1")
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

    # --- Deep health endpoint (expensive: LLM + embedding + Qdrant stats) ---
    @application.get("/api/v1/health/deep", tags=["system"])
    async def health_deep(request: Request) -> JSONResponse:
        """Extended health check that probes LLM, embedding, and Qdrant collections.

        Slower than ``/health`` — makes a real LLM completion call and an
        embedding call. Use for diagnostics, not load-balancer checks.
        """
        import time

        services: dict[str, dict[str, Any]] = {}

        # LLM completion
        try:
            llm = get_llm()
            start = time.perf_counter()
            response = await llm.complete(
                [{"role": "user", "content": "Reply with the single word OK."}],
                max_tokens=4,
                temperature=0,
            )
            latency_ms = round((time.perf_counter() - start) * 1000)
            services["llm"] = {
                "status": "ok",
                "provider": llm.provider,
                "model": llm.model,
                "latency_ms": latency_ms,
                "response_preview": response[:50],
            }
        except Exception as exc:
            services["llm"] = {"status": f"error: {exc}"}

        # Embedding
        try:
            embedder = get_embedder()
            start = time.perf_counter()
            vec = await embedder.embed_query("health check")
            latency_ms = round((time.perf_counter() - start) * 1000)
            settings = get_settings()
            services["embedding"] = {
                "status": "ok",
                "provider": settings.embedding_provider,
                "dimensions": len(vec),
                "expected_dimensions": settings.embedding_dimensions,
                "latency_ms": latency_ms,
            }
        except Exception as exc:
            services["embedding"] = {"status": f"error: {exc}"}

        # Qdrant collection stats
        try:
            qdrant = get_qdrant()
            info = await qdrant.get_collection_info("nexus_text")
            services["qdrant_nexus_text"] = {"status": "ok", **info}
        except Exception as exc:
            services["qdrant_nexus_text"] = {"status": f"error: {exc}"}

        all_ok = all((v.get("status") == "ok" if isinstance(v, dict) else v == "ok") for v in services.values())
        return JSONResponse(
            status_code=200 if all_ok else 503,
            content={"status": "healthy" if all_ok else "degraded", "services": services},
        )

    # --- Feature flags endpoint ---
    class FeatureFlagsResponse(BaseModel):
        hot_doc_detection: bool
        case_setup_agent: bool
        topic_clustering: bool
        graph_centrality: bool
        sparse_embeddings: bool
        near_duplicate_detection: bool
        reranker: bool
        redaction: bool

    @application.get("/api/v1/config/features", response_model=FeatureFlagsResponse, tags=["system"])
    async def get_feature_flags(
        current_user: Any = Depends(get_current_user),
    ) -> FeatureFlagsResponse:
        """Return user-visible feature flag states."""
        settings = get_settings()
        return FeatureFlagsResponse(
            hot_doc_detection=settings.enable_hot_doc_detection,
            case_setup_agent=settings.enable_case_setup_agent,
            topic_clustering=settings.enable_topic_clustering,
            graph_centrality=settings.enable_graph_centrality,
            sparse_embeddings=settings.enable_sparse_embeddings,
            near_duplicate_detection=settings.enable_near_duplicate_detection,
            reranker=settings.enable_reranker,
            redaction=settings.enable_redaction,
        )

    return application


# Module-level app instance used by ``uvicorn app.main:app``
app = create_app()
