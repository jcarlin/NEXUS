"""FastAPI dependency injection providers.

Module-level singletons are initialised once (on first call or during lifespan)
and reused across requests.  The ``get_*`` functions are meant to be used as
FastAPI ``Depends()`` callables.
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
    LocalEmbeddingProvider,
    OpenAIEmbeddingProvider,
)
from app.common.llm import LLMClient
from app.common.storage import StorageClient
from app.common.vector_store import VectorStoreClient
from app.config import Settings
from app.entities.extractor import EntityExtractor
from app.entities.graph_service import GraphService
from app.ingestion.sparse_embedder import SparseEmbedder
from app.ingestion.visual_embedder import VisualEmbedder
from app.query.reranker import Reranker
from app.query.retriever import HybridRetriever

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Settings (cached singleton)
# ---------------------------------------------------------------------------


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the application Settings singleton."""
    return Settings()


# ---------------------------------------------------------------------------
# PostgreSQL (async SQLAlchemy)
# ---------------------------------------------------------------------------

_async_engine = None
_async_session_factory: async_sessionmaker[AsyncSession] | None = None


def _get_engine():
    global _async_engine
    if _async_engine is None:
        settings = get_settings()
        _async_engine = create_async_engine(
            settings.postgres_url,
            echo=False,
            pool_size=5,
            max_overflow=10,
        )
    return _async_engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _async_session_factory
    if _async_session_factory is None:
        _async_session_factory = async_sessionmaker(
            bind=_get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _async_session_factory


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

_qdrant_client: VectorStoreClient | None = None


def get_qdrant() -> VectorStoreClient:
    """Return the Qdrant wrapper singleton."""
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = VectorStoreClient(get_settings())
    return _qdrant_client


# ---------------------------------------------------------------------------
# Neo4j
# ---------------------------------------------------------------------------

_neo4j_driver = None


def get_neo4j():
    """Return an ``AsyncDriver`` for Neo4j."""
    global _neo4j_driver
    if _neo4j_driver is None:
        settings = get_settings()
        _neo4j_driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
    return _neo4j_driver


# ---------------------------------------------------------------------------
# MinIO / S3
# ---------------------------------------------------------------------------

_storage_client: StorageClient | None = None


def get_minio() -> StorageClient:
    """Return the MinIO ``StorageClient`` singleton."""
    global _storage_client
    if _storage_client is None:
        _storage_client = StorageClient(get_settings())
    return _storage_client


# ---------------------------------------------------------------------------
# Redis
# ---------------------------------------------------------------------------

_redis_client: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    """Return an async Redis client singleton."""
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis_client


# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------

_llm_client: LLMClient | None = None


def get_llm() -> LLMClient:
    """Return the ``LLMClient`` singleton."""
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient(get_settings())
    return _llm_client


# ---------------------------------------------------------------------------
# Text Embedder
# ---------------------------------------------------------------------------

_embedder: EmbeddingProvider | None = None


def get_embedder() -> EmbeddingProvider:
    """Return the embedding provider singleton based on ``EMBEDDING_PROVIDER`` config."""
    global _embedder
    if _embedder is None:
        settings = get_settings()
        if settings.embedding_provider == "local":
            _embedder = LocalEmbeddingProvider(
                model_name=settings.local_embedding_model,
                dimensions=settings.embedding_dimensions,
            )
        else:
            _embedder = OpenAIEmbeddingProvider(
                api_key=settings.openai_api_key,
                model=settings.embedding_model,
                dimensions=settings.embedding_dimensions,
                batch_size=settings.embedding_batch_size,
            )
    return _embedder


# ---------------------------------------------------------------------------
# Graph Service
# ---------------------------------------------------------------------------

_graph_service: GraphService | None = None


def get_graph_service() -> GraphService:
    """Return the ``GraphService`` singleton (wraps Neo4j driver)."""
    global _graph_service
    if _graph_service is None:
        _graph_service = GraphService(get_neo4j())
    return _graph_service


# ---------------------------------------------------------------------------
# Entity Extractor
# ---------------------------------------------------------------------------

_entity_extractor: EntityExtractor | None = None


def get_entity_extractor() -> EntityExtractor:
    """Return the ``EntityExtractor`` singleton (GLiNER, lazy-loads model)."""
    global _entity_extractor
    if _entity_extractor is None:
        settings = get_settings()
        _entity_extractor = EntityExtractor(model_name=settings.gliner_model)
    return _entity_extractor


# ---------------------------------------------------------------------------
# Reranker (feature-flagged)
# ---------------------------------------------------------------------------

_reranker: Reranker | None = None


def get_reranker() -> Reranker | None:
    """Return the ``Reranker`` singleton, or ``None`` when disabled."""
    global _reranker
    settings = get_settings()
    if not settings.enable_reranker:
        return None
    if _reranker is None:
        _reranker = Reranker(model_name=settings.reranker_model)
    return _reranker


# ---------------------------------------------------------------------------
# Sparse Embedder (feature-flagged)
# ---------------------------------------------------------------------------

_sparse_embedder: SparseEmbedder | None = None


def get_sparse_embedder() -> SparseEmbedder | None:
    """Return the ``SparseEmbedder`` singleton, or ``None`` when disabled."""
    global _sparse_embedder
    settings = get_settings()
    if not settings.enable_sparse_embeddings:
        return None
    if _sparse_embedder is None:
        _sparse_embedder = SparseEmbedder(model_name=settings.sparse_embedding_model)
    return _sparse_embedder


# ---------------------------------------------------------------------------
# Visual Embedder (feature-flagged)
# ---------------------------------------------------------------------------

_visual_embedder: VisualEmbedder | None = None


def get_visual_embedder() -> VisualEmbedder | None:
    """Return the ``VisualEmbedder`` singleton, or ``None`` when disabled."""
    global _visual_embedder
    settings = get_settings()
    if not settings.enable_visual_embeddings:
        return None
    if _visual_embedder is None:
        _visual_embedder = VisualEmbedder(
            model_name=settings.visual_embedding_model,
            device=settings.visual_embedding_device,
        )
    return _visual_embedder


# ---------------------------------------------------------------------------
# Near-Duplicate Detector (feature-flagged)
# ---------------------------------------------------------------------------

_dedup_detector = None


def get_dedup_detector():
    """Return the ``NearDuplicateDetector`` singleton, or ``None`` when disabled."""
    global _dedup_detector
    settings = get_settings()
    if not settings.enable_near_duplicate_detection:
        return None
    if _dedup_detector is None:
        from app.ingestion.dedup import NearDuplicateDetector

        _dedup_detector = NearDuplicateDetector(
            threshold=settings.dedup_jaccard_threshold,
            num_perm=settings.dedup_num_permutations,
        )
    return _dedup_detector


# ---------------------------------------------------------------------------
# Coreference Resolver (feature-flagged)
# ---------------------------------------------------------------------------

_coref_resolver = None


def get_coref_resolver():
    """Return the ``CoreferenceResolver`` singleton, or ``None`` when disabled."""
    global _coref_resolver
    settings = get_settings()
    if not settings.enable_coreference_resolution:
        return None
    if _coref_resolver is None:
        from app.entities.coreference import CoreferenceResolver

        _coref_resolver = CoreferenceResolver(model_name=settings.coreference_model)
    return _coref_resolver


# ---------------------------------------------------------------------------
# Hybrid Retriever
# ---------------------------------------------------------------------------

_retriever: HybridRetriever | None = None


def get_retriever() -> HybridRetriever:
    """Return the ``HybridRetriever`` singleton."""
    global _retriever
    if _retriever is None:
        _retriever = HybridRetriever(
            embedder=get_embedder(),
            vector_store=get_qdrant(),
            entity_extractor=get_entity_extractor(),
            graph_service=get_graph_service(),
            sparse_embedder=get_sparse_embedder(),
            visual_embedder=get_visual_embedder(),
        )
    return _retriever


# ---------------------------------------------------------------------------
# LangGraph Checkpointer (sync psycopg connection)
# ---------------------------------------------------------------------------

_checkpointer = None
_checkpointer_conn = None


def get_checkpointer():
    """Return the PostgresSaver checkpointer singleton.

    Uses a synchronous ``psycopg`` connection with ``autocommit=True``.
    The ``.setup()`` call is idempotent — it creates checkpoint tables if they
    don't already exist.
    """
    global _checkpointer, _checkpointer_conn
    if _checkpointer is None:
        import psycopg
        from langgraph.checkpoint.postgres import PostgresSaver

        settings = get_settings()
        _checkpointer_conn = psycopg.connect(settings.postgres_url_sync, autocommit=True)
        _checkpointer = PostgresSaver(conn=_checkpointer_conn)
        _checkpointer.setup()
    return _checkpointer


# ---------------------------------------------------------------------------
# Query Graph (compiled LangGraph)
# ---------------------------------------------------------------------------

_query_graph = None


def get_query_graph():
    """Return the compiled investigation ``StateGraph`` singleton.

    Uses the agentic pipeline when ``enable_agentic_pipeline`` is set,
    otherwise falls back to the v1 9-node chain.
    """
    global _query_graph
    if _query_graph is None:
        settings = get_settings()
        if settings.enable_agentic_pipeline:
            from app.query.graph import build_agentic_graph

            _query_graph = build_agentic_graph(settings, get_checkpointer())
        else:
            from app.query.graph import build_graph_v1

            _query_graph = build_graph_v1(
                llm=get_llm(),
                retriever=get_retriever(),
                graph_service=get_graph_service(),
                entity_extractor=get_entity_extractor(),
            ).compile(checkpointer=get_checkpointer())
    return _query_graph


# ---------------------------------------------------------------------------
# Cleanup (called from lifespan shutdown)
# ---------------------------------------------------------------------------


async def close_all() -> None:
    """Gracefully tear down all shared clients."""
    global _async_engine, _neo4j_driver, _redis_client, _checkpointer, _checkpointer_conn

    if _checkpointer_conn is not None:
        try:
            _checkpointer_conn.close()
        except Exception:
            pass
        _checkpointer_conn = None
        _checkpointer = None
        logger.info("shutdown.checkpointer")

    if _async_engine is not None:
        await _async_engine.dispose()
        _async_engine = None
        logger.info("shutdown.postgres")

    if _neo4j_driver is not None:
        await _neo4j_driver.close()
        _neo4j_driver = None
        logger.info("shutdown.neo4j")

    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
        logger.info("shutdown.redis")

    logger.info("shutdown.complete")
