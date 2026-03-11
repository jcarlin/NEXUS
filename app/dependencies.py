"""FastAPI dependency injection providers.

Singletons are created on first call via ``@functools.cache`` and reused across
requests.  The ``get_*`` functions are meant to be used as FastAPI ``Depends()``
callables.  Call ``close_all()`` during lifespan shutdown to release resources
and clear every cache.
"""

from __future__ import annotations

import functools
from collections.abc import AsyncIterator

import redis.asyncio as aioredis
import structlog
from neo4j import AsyncGraphDatabase
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.common.embedder import (
    EmbeddingProvider,
    GeminiEmbeddingProvider,
    LocalEmbeddingProvider,
    OllamaEmbeddingProvider,
    OpenAIEmbeddingProvider,
    TEIEmbeddingProvider,
)
from app.common.llm import LLMClient
from app.common.storage import StorageClient
from app.common.vector_store import VectorStoreClient
from app.config import Settings
from app.entities.extractor import EntityExtractor
from app.entities.graph_service import GraphService
from app.ingestion.sparse_embedder import SparseEmbedder
from app.ingestion.visual_embedder import VisualEmbedder
from app.query.reranker import Reranker, TEIReranker
from app.query.retriever import HybridRetriever

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Settings (cached singleton)
# ---------------------------------------------------------------------------


@functools.cache
def get_settings() -> Settings:
    """Return the application Settings singleton."""
    return Settings()


# ---------------------------------------------------------------------------
# PostgreSQL (async SQLAlchemy)
# ---------------------------------------------------------------------------


@functools.cache
def _get_engine():
    settings = get_settings()
    return create_async_engine(
        settings.postgres_url,
        echo=False,
        pool_size=5,
        max_overflow=10,
    )


@functools.cache
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=_get_engine(),
        class_=AsyncSession,
        expire_on_commit=False,
    )


async def get_db() -> AsyncIterator[AsyncSession]:
    """Yield an ``AsyncSession`` scoped to a single request."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ---------------------------------------------------------------------------
# Qdrant
# ---------------------------------------------------------------------------


@functools.cache
def get_qdrant() -> VectorStoreClient:
    """Return the Qdrant wrapper singleton."""
    return VectorStoreClient(get_settings())


# ---------------------------------------------------------------------------
# Neo4j
# ---------------------------------------------------------------------------


@functools.cache
def get_neo4j():
    """Return an ``AsyncDriver`` for Neo4j."""
    settings = get_settings()
    return AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )


# ---------------------------------------------------------------------------
# MinIO / S3
# ---------------------------------------------------------------------------


@functools.cache
def get_minio() -> StorageClient:
    """Return the MinIO ``StorageClient`` singleton."""
    return StorageClient(get_settings())


# ---------------------------------------------------------------------------
# Redis
# ---------------------------------------------------------------------------


@functools.cache
def get_redis() -> aioredis.Redis:
    """Return an async Redis client singleton."""
    settings = get_settings()
    return aioredis.from_url(settings.redis_url, decode_responses=True)


# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------


@functools.cache
def get_llm() -> LLMClient:
    """Return the ``LLMClient`` singleton.

    Checks the DB for admin-configured LLM provider/model overrides first
    (set via /admin/llm-settings).  Falls back to env-var Settings if no
    DB override exists.  The ``/apply`` endpoint calls
    ``get_llm.cache_clear()`` so changes take effect on next request.
    """
    settings = get_settings()
    from sqlalchemy import create_engine

    from app.llm_config.resolver import resolve_llm_config_sync

    engine = create_engine(settings.postgres_url_sync, pool_pre_ping=True)
    try:
        config = resolve_llm_config_sync("query", engine)
    finally:
        engine.dispose()
    return LLMClient.from_resolved_config(config)


# Module-level pool for tier-resolved LLM clients (keyed by provider/model/base_url)
_llm_pool: dict[tuple[str, str, str | None], LLMClient] = {}


async def get_llm_for_tier(tier: str, db: AsyncSession) -> LLMClient:
    """Resolve LLM config for a tier and return an LLMClient.

    Uses a pool keyed by (provider, model, base_url) to reuse HTTP clients.
    """
    from app.llm_config.resolver import resolve_llm_config

    config = await resolve_llm_config(tier, db)

    cache_key = (config.provider, config.model, config.base_url)
    if cache_key not in _llm_pool:
        _llm_pool[cache_key] = LLMClient.from_resolved_config(config)
    return _llm_pool[cache_key]


# ---------------------------------------------------------------------------
# Text Embedder
# ---------------------------------------------------------------------------


@functools.cache
def get_embedder() -> EmbeddingProvider:
    """Return the embedding provider singleton based on ``EMBEDDING_PROVIDER`` config."""
    settings = get_settings()
    if settings.embedding_provider == "local":
        return LocalEmbeddingProvider(
            model_name=settings.local_embedding_model,
            dimensions=settings.embedding_dimensions,
        )
    if settings.embedding_provider == "tei":
        return TEIEmbeddingProvider(
            base_url=settings.tei_embedding_url,
            dimensions=settings.embedding_dimensions,
        )
    if settings.embedding_provider == "gemini":
        return GeminiEmbeddingProvider(
            api_key=settings.gemini_api_key,
            model=settings.gemini_embedding_model,
            dimensions=settings.embedding_dimensions,
            batch_size=settings.embedding_batch_size,
        )
    if settings.embedding_provider == "ollama":
        return OllamaEmbeddingProvider(
            base_url=settings.ollama_base_url.removesuffix("/v1"),
            model=settings.ollama_embedding_model,
            dimensions=settings.embedding_dimensions,
        )
    return OpenAIEmbeddingProvider(
        api_key=settings.openai_api_key,
        model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
        batch_size=settings.embedding_batch_size,
    )


# ---------------------------------------------------------------------------
# Graph Service
# ---------------------------------------------------------------------------


@functools.cache
def get_graph_service() -> GraphService:
    """Return the ``GraphService`` singleton (wraps Neo4j driver)."""
    return GraphService(get_neo4j())


# ---------------------------------------------------------------------------
# Entity Extractor
# ---------------------------------------------------------------------------


@functools.cache
def get_entity_extractor() -> EntityExtractor:
    """Return the ``EntityExtractor`` singleton (GLiNER, lazy-loads model)."""
    settings = get_settings()
    return EntityExtractor(model_name=settings.gliner_model)


# ---------------------------------------------------------------------------
# Reranker (feature-flagged)
# ---------------------------------------------------------------------------


@functools.cache
def get_reranker() -> Reranker | TEIReranker | None:
    """Return the ``Reranker`` singleton, or ``None`` when disabled."""
    settings = get_settings()
    if not settings.enable_reranker:
        return None
    if settings.reranker_provider == "tei":
        return TEIReranker(base_url=settings.tei_reranker_url)
    return Reranker(model_name=settings.reranker_model)


# ---------------------------------------------------------------------------
# Sparse Embedder (feature-flagged)
# ---------------------------------------------------------------------------


@functools.cache
def get_sparse_embedder() -> SparseEmbedder | None:
    """Return the ``SparseEmbedder`` singleton, or ``None`` when disabled."""
    settings = get_settings()
    if not settings.enable_sparse_embeddings:
        return None
    return SparseEmbedder(model_name=settings.sparse_embedding_model)


# ---------------------------------------------------------------------------
# Visual Embedder (feature-flagged)
# ---------------------------------------------------------------------------


@functools.cache
def get_visual_embedder() -> VisualEmbedder | None:
    """Return the ``VisualEmbedder`` singleton, or ``None`` when disabled."""
    settings = get_settings()
    if not settings.enable_visual_embeddings:
        return None
    return VisualEmbedder(
        model_name=settings.visual_embedding_model,
        device=settings.visual_embedding_device,
    )


# ---------------------------------------------------------------------------
# Near-Duplicate Detector (feature-flagged)
# ---------------------------------------------------------------------------


@functools.cache
def get_dedup_detector():
    """Return the ``NearDuplicateDetector`` singleton, or ``None`` when disabled."""
    settings = get_settings()
    if not settings.enable_near_duplicate_detection:
        return None
    from app.ingestion.dedup import NearDuplicateDetector

    return NearDuplicateDetector(
        threshold=settings.dedup_jaccard_threshold,
        num_perm=settings.dedup_num_permutations,
    )


# ---------------------------------------------------------------------------
# Coreference Resolver (feature-flagged)
# ---------------------------------------------------------------------------


@functools.cache
def get_coref_resolver():
    """Return the ``CoreferenceResolver`` singleton, or ``None`` when disabled."""
    settings = get_settings()
    if not settings.enable_coreference_resolution:
        return None
    from app.entities.coreference import CoreferenceResolver

    return CoreferenceResolver(model_name=settings.coreference_model)


# ---------------------------------------------------------------------------
# Google Drive Service (feature-flagged)
# ---------------------------------------------------------------------------


@functools.cache
def get_gdrive_service():
    """Return the ``GDriveService`` singleton, or ``None`` when disabled."""
    settings = get_settings()
    if not settings.enable_google_drive:
        return None
    from app.gdrive.service import GDriveService

    return GDriveService(settings)


# ---------------------------------------------------------------------------
# OIDC Provider (feature-flagged)
# ---------------------------------------------------------------------------


@functools.cache
def get_oidc_provider():
    """Return the ``OIDCProvider`` singleton, or ``None`` when disabled."""
    settings = get_settings()
    if not settings.enable_sso:
        return None
    from app.auth.oidc import OIDCProvider

    return OIDCProvider(settings)


# ---------------------------------------------------------------------------
# Hybrid Retriever
# ---------------------------------------------------------------------------


@functools.cache
def get_retriever() -> HybridRetriever:
    """Return the ``HybridRetriever`` singleton."""
    return HybridRetriever(
        embedder=get_embedder(),
        vector_store=get_qdrant(),
        entity_extractor=get_entity_extractor(),
        graph_service=get_graph_service(),
        sparse_embedder=get_sparse_embedder(),
        visual_embedder=get_visual_embedder(),
    )


# ---------------------------------------------------------------------------
# LangGraph Checkpointer (sync psycopg connection)
# ---------------------------------------------------------------------------


@functools.cache
def _get_checkpointer_conn():
    """Return a synchronous ``psycopg`` connection for the checkpointer.

    Used only by ``_setup_checkpointer_tables`` to create tables synchronously
    at startup. The async checkpointer uses its own pool.
    """
    import psycopg

    settings = get_settings()
    return psycopg.connect(settings.postgres_url_sync, autocommit=True)


@functools.cache
def get_checkpointer():
    """Return the AsyncPostgresSaver checkpointer singleton.

    Uses ``AsyncConnectionPool`` so that ``graph.astream()`` can call
    async checkpoint methods (``aget_tuple``, ``aput``, etc.).
    The sync connection is used once at startup for table creation.
    """
    from langgraph.checkpoint.postgres import PostgresSaver
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from psycopg_pool import AsyncConnectionPool

    # Create tables synchronously (idempotent)
    sync_conn = _get_checkpointer_conn()
    sync_saver = PostgresSaver(conn=sync_conn)
    sync_saver.setup()

    # Build async checkpointer with a connection pool
    settings = get_settings()
    pool = AsyncConnectionPool(
        conninfo=settings.postgres_url_sync,
        min_size=1,
        max_size=5,
        kwargs={"autocommit": True},
    )
    return AsyncPostgresSaver(pool)


# ---------------------------------------------------------------------------
# Query Graph (compiled LangGraph)
# ---------------------------------------------------------------------------


@functools.cache
def get_query_graph():
    """Return the compiled investigation ``StateGraph`` singleton.

    Uses the agentic pipeline when ``enable_agentic_pipeline`` is set,
    otherwise falls back to the v1 9-node chain.
    """
    settings = get_settings()
    if settings.enable_agentic_pipeline:
        from app.query.graph import build_agentic_graph

        return build_agentic_graph(settings, get_checkpointer())

    from app.query.graph import build_graph_v1

    return build_graph_v1(
        llm=get_llm(),
        retriever=get_retriever(),
        graph_service=get_graph_service(),
        entity_extractor=get_entity_extractor(),
    ).compile(checkpointer=get_checkpointer())


# ---------------------------------------------------------------------------
# All cached factory functions (for bulk cache_clear in close_all)
# ---------------------------------------------------------------------------

_ALL_CACHED_FACTORIES = [
    get_settings,
    _get_engine,
    get_session_factory,
    get_qdrant,
    get_neo4j,
    get_minio,
    get_redis,
    get_llm,
    get_embedder,
    get_graph_service,
    get_entity_extractor,
    get_reranker,
    get_sparse_embedder,
    get_visual_embedder,
    get_dedup_detector,
    get_coref_resolver,
    get_retriever,
    get_gdrive_service,
    get_oidc_provider,
    _get_checkpointer_conn,
    get_checkpointer,
    get_query_graph,
]


# ---------------------------------------------------------------------------
# Cleanup (called from lifespan shutdown)
# ---------------------------------------------------------------------------


async def close_all() -> None:
    """Gracefully tear down all shared clients and clear caches."""

    # Close checkpointer connection
    if _get_checkpointer_conn.cache_info().currsize:
        try:
            _get_checkpointer_conn().close()
        except Exception:
            pass
        logger.info("shutdown.checkpointer")

    # Dispose async engine
    if _get_engine.cache_info().currsize:
        await _get_engine().dispose()
        logger.info("shutdown.postgres")

    # Close Neo4j driver
    if get_neo4j.cache_info().currsize:
        try:
            await get_neo4j().close()
        except Exception:
            pass
        logger.info("shutdown.neo4j")

    # Close Redis
    if get_redis.cache_info().currsize:
        await get_redis().aclose()
        logger.info("shutdown.redis")

    # Close TEI HTTP clients (embedder and reranker)
    if get_embedder.cache_info().currsize:
        embedder = get_embedder()
        if hasattr(embedder, "close"):
            await embedder.close()
            logger.info("shutdown.tei_embedder")

    if get_reranker.cache_info().currsize:
        reranker = get_reranker()
        if reranker is not None and hasattr(reranker, "close"):
            await reranker.close()
            logger.info("shutdown.tei_reranker")

    # Clear all caches
    for fn in _ALL_CACHED_FACTORIES:
        fn.cache_clear()

    # Clear tier-resolved LLM pool
    _llm_pool.clear()

    logger.info("shutdown.complete")
