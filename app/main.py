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
    import asyncio

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

    # --- Group 1: Infrastructure init (all independent) ---
    async def _init_qdrant() -> None:
        try:
            qdrant = get_qdrant()
            await qdrant.ensure_collections()
            logger.info("startup.qdrant.ok")
        except Exception as exc:
            logger.error("startup.qdrant.failed", error=str(exc))

    async def _init_minio() -> None:
        try:
            storage = get_minio()
            await storage.ensure_bucket()
            logger.info("startup.minio.ok")
        except Exception as exc:
            logger.error("startup.minio.failed", error=str(exc))

    async def _init_neo4j() -> None:
        try:
            driver = get_neo4j()
            async with driver.session() as session:
                result = await session.run("RETURN 1 AS n")
                await result.consume()
            logger.info("startup.neo4j.ok")

            from app.entities.schema import ensure_schema

            await ensure_schema(driver)
            logger.info("startup.neo4j.schema.ok")
        except Exception as exc:
            logger.error("startup.neo4j.failed", error=str(exc))

    async def _init_redis() -> None:
        try:
            redis = get_redis()
            await redis.ping()
            logger.info("startup.redis.ok")
        except Exception as exc:
            logger.error("startup.redis.failed", error=str(exc))

    async def _init_postgres() -> None:
        try:
            from sqlalchemy import text as sa_text

            from app.dependencies import _get_engine

            engine = _get_engine()
            async with engine.connect() as conn:
                await conn.execute(sa_text("SELECT 1"))
            logger.info("startup.postgres.ok")
        except Exception as exc:
            logger.error("startup.postgres.failed", error=str(exc))

    await asyncio.gather(
        _init_qdrant(),
        _init_minio(),
        _init_neo4j(),
        _init_redis(),
        _init_postgres(),
    )

    # --- Group 2: Depends on postgres being ready ---
    async def _init_checkpointer() -> None:
        try:
            from app.dependencies import get_checkpointer

            get_checkpointer()
            logger.info("startup.checkpointer.ok")
        except Exception as exc:
            logger.error("startup.checkpointer.failed", error=str(exc))

    async def _init_feature_flags() -> None:
        try:
            from app.dependencies import get_session_factory
            from app.feature_flags.service import FeatureFlagService

            factory = get_session_factory()
            async with factory() as session:
                await FeatureFlagService.load_overrides_into_settings(session)
                await session.commit()
            logger.info("startup.feature_flags.ok")
        except Exception as exc:
            logger.error("startup.feature_flags.failed", error=str(exc))

    async def _init_setting_overrides() -> None:
        try:
            from app.dependencies import get_session_factory
            from app.settings_registry.service import SettingsRegistryService

            factory = get_session_factory()
            async with factory() as session:
                await SettingsRegistryService.load_overrides_into_settings(session)
                await session.commit()
            logger.info("startup.setting_overrides.ok")
        except Exception as exc:
            logger.error("startup.setting_overrides.failed", error=str(exc))

    await asyncio.gather(_init_checkpointer(), _init_feature_flags(), _init_setting_overrides())

    # --- Group 3: Model warmup (independent, can be CPU-bound) ---
    async def _warmup_embedder() -> None:
        try:
            embedder = get_embedder()
            await embedder.embed_query("warmup")
            logger.info("startup.embedder.ok")
        except Exception as exc:
            logger.error("startup.embedder.failed", error=str(exc))

    async def _warmup_gliner() -> None:
        try:
            from app.dependencies import get_entity_extractor

            extractor = get_entity_extractor()
            await asyncio.to_thread(
                extractor.extract,
                "warmup",
                entity_types=["person"],
                threshold=0.99,
            )
            logger.info("startup.gliner.ok")
        except Exception as exc:
            logger.error("startup.gliner.failed", error=str(exc))

    await asyncio.gather(_warmup_embedder(), _warmup_gliner())

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

    # --- Feature-flagged middleware ---
    settings = get_settings()

    # Load DB feature flag overrides before conditional router registration.
    # Restart-level flags gate router mounting below. Without this early sync
    # load, DB overrides set via the admin UI would never take effect because
    # lifespan() runs after create_app().
    try:
        from sqlalchemy import create_engine

        from app.feature_flags.service import load_overrides_sync_safe
        from app.settings_registry.service import load_setting_overrides_sync_safe

        _sync_engine = create_engine(settings.postgres_url_sync, pool_pre_ping=True)
        try:
            load_overrides_sync_safe(settings, _sync_engine)
            load_setting_overrides_sync_safe(settings, _sync_engine)
        finally:
            _sync_engine.dispose()
    except Exception:
        logger.warning("startup.feature_flags.early_load.failed", exc_info=True)

    if settings.enable_prometheus_metrics:
        from prometheus_fastapi_instrumentator import Instrumentator

        Instrumentator().instrument(application).expose(application, endpoint="/metrics")

    # --- Feature-flagged routers ---
    if settings.enable_google_drive:
        from app.gdrive.router import router as gdrive_router

        application.include_router(gdrive_router, prefix="/api/v1")

    from app.auth.oidc_router import router as oidc_router

    application.include_router(oidc_router, prefix="/api/v1")

    from app.auth.saml_router import router as saml_router

    application.include_router(saml_router, prefix="/api/v1")

    if settings.enable_memo_drafting:
        from app.memos.router import router as memos_router

        application.include_router(memos_router, prefix="/api/v1")

    if settings.enable_deposition_prep:
        from app.depositions.router import router as depositions_router

        application.include_router(depositions_router, prefix="/api/v1")

    if settings.enable_service_operations:
        from app.operations.router import router as operations_router

        application.include_router(operations_router, prefix="/api/v1")

    from app.retention.router import router as retention_router

    application.include_router(retention_router, prefix="/api/v1")

    # LLM runtime configuration (always enabled — admin-only access enforced in router)
    from app.llm_config.public_router import router as llm_config_public_router
    from app.llm_config.router import router as llm_config_router

    application.include_router(llm_config_router, prefix="/api/v1")
    application.include_router(llm_config_public_router, prefix="/api/v1")

    # Feature flag runtime management (always enabled — admin-only access enforced in router)
    from app.feature_flags.router import router as feature_flags_router

    application.include_router(feature_flags_router, prefix="/api/v1")

    # Settings registry runtime management (always enabled — admin-only access enforced in router)
    from app.settings_registry.router import router as settings_registry_router

    application.include_router(settings_registry_router, prefix="/api/v1")

    # --- Health endpoint ---
    @application.get("/api/v1/health", tags=["system"])
    async def health(request: Request) -> JSONResponse:
        """Ping all five backing services in parallel and report their status."""
        import asyncio

        health_timeout = 5.0  # seconds per service check

        async def _check_qdrant() -> tuple[str, str]:
            try:
                qdrant = get_qdrant()
                await asyncio.wait_for(
                    asyncio.to_thread(qdrant.client.get_collections),
                    timeout=health_timeout,
                )
                return ("qdrant", "ok")
            except TimeoutError:
                return ("qdrant", "error: timeout")
            except Exception as exc:
                return ("qdrant", f"error: {exc}")

        async def _check_minio() -> tuple[str, str]:
            try:
                storage = get_minio()
                await asyncio.wait_for(
                    storage.list_objects(prefix=""),
                    timeout=health_timeout,
                )
                return ("minio", "ok")
            except TimeoutError:
                return ("minio", "error: timeout")
            except Exception as exc:
                return ("minio", f"error: {exc}")

        async def _check_neo4j() -> tuple[str, str]:
            try:

                async def _neo4j_ping() -> None:
                    driver = get_neo4j()
                    async with driver.session() as session:
                        result = await session.run("RETURN 1 AS n")
                        await result.consume()

                await asyncio.wait_for(_neo4j_ping(), timeout=health_timeout)
                return ("neo4j", "ok")
            except TimeoutError:
                return ("neo4j", "error: timeout")
            except Exception as exc:
                return ("neo4j", f"error: {exc}")

        async def _check_redis() -> tuple[str, str]:
            try:
                redis = get_redis()
                await asyncio.wait_for(redis.ping(), timeout=health_timeout)
                return ("redis", "ok")
            except TimeoutError:
                return ("redis", "error: timeout")
            except Exception as exc:
                return ("redis", f"error: {exc}")

        async def _check_postgres() -> tuple[str, str]:
            try:
                from sqlalchemy import text as sa_text

                from app.dependencies import _get_engine

                async def _pg_ping() -> None:
                    engine = _get_engine()
                    async with engine.connect() as conn:
                        await conn.execute(sa_text("SELECT 1"))

                await asyncio.wait_for(_pg_ping(), timeout=health_timeout)
                return ("postgres", "ok")
            except TimeoutError:
                return ("postgres", "error: timeout")
            except Exception as exc:
                return ("postgres", f"error: {exc}")

        results = await asyncio.gather(
            _check_qdrant(),
            _check_minio(),
            _check_neo4j(),
            _check_redis(),
            _check_postgres(),
        )
        status = dict(results)

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
            services["qdrant_nexus_text"] = {**info, "status": "ok"}
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
        visual_embeddings: bool
        relationship_extraction: bool
        email_threading: bool
        ai_audit_logging: bool
        coreference_resolution: bool
        batch_embeddings: bool
        agentic_pipeline: bool
        citation_verification: bool
        google_drive: bool
        prometheus_metrics: bool
        sso: bool
        saml: bool
        memo_drafting: bool
        chunk_quality_scoring: bool
        contextual_chunks: bool
        retrieval_grading: bool
        multi_query_expansion: bool
        text_to_cypher: bool
        prompt_routing: bool
        question_decomposition: bool
        retrieval_overrides: bool
        page_chat: bool
        page_documents: bool
        page_ingest: bool
        page_datasets: bool
        page_entities: bool
        page_comms_matrix: bool
        page_timeline: bool
        page_network_graph: bool
        page_hot_docs: bool
        page_result_set: bool
        page_exports: bool
        page_case_setup: bool

    @application.get("/api/v1/config/features", response_model=FeatureFlagsResponse, tags=["system"])
    async def get_feature_flags(
        current_user: Any = Depends(get_current_user),
    ) -> FeatureFlagsResponse:
        """Return user-visible feature flag states (reflects DB overrides)."""
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
            visual_embeddings=settings.enable_visual_embeddings,
            relationship_extraction=settings.enable_relationship_extraction,
            email_threading=settings.enable_email_threading,
            ai_audit_logging=settings.enable_ai_audit_logging,
            coreference_resolution=settings.enable_coreference_resolution,
            batch_embeddings=settings.enable_batch_embeddings,
            agentic_pipeline=settings.enable_agentic_pipeline,
            citation_verification=settings.enable_citation_verification,
            google_drive=settings.enable_google_drive,
            prometheus_metrics=settings.enable_prometheus_metrics,
            sso=settings.enable_sso,
            saml=settings.enable_saml,
            memo_drafting=settings.enable_memo_drafting,
            chunk_quality_scoring=settings.enable_chunk_quality_scoring,
            contextual_chunks=settings.enable_contextual_chunks,
            retrieval_grading=settings.enable_retrieval_grading,
            multi_query_expansion=settings.enable_multi_query_expansion,
            text_to_cypher=settings.enable_text_to_cypher,
            prompt_routing=settings.enable_prompt_routing,
            question_decomposition=settings.enable_question_decomposition,
            retrieval_overrides=settings.enable_retrieval_overrides,
            page_chat=settings.enable_page_chat,
            page_documents=settings.enable_page_documents,
            page_ingest=settings.enable_page_ingest,
            page_datasets=settings.enable_page_datasets,
            page_entities=settings.enable_page_entities,
            page_comms_matrix=settings.enable_page_comms_matrix,
            page_timeline=settings.enable_page_timeline,
            page_network_graph=settings.enable_page_network_graph,
            page_hot_docs=settings.enable_page_hot_docs,
            page_result_set=settings.enable_page_result_set,
            page_exports=settings.enable_page_exports,
            page_case_setup=settings.enable_page_case_setup,
        )

    return application


# Module-level app instance used by ``uvicorn app.main:app``
app = create_app()
