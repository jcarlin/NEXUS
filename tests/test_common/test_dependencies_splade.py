"""Tests for SPLADE integration in get_sparse_embedder() DI factory."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.config import Settings


def _make_test_settings(**overrides) -> Settings:
    """Build a ``Settings`` instance with safe defaults for testing."""
    defaults = dict(
        anthropic_api_key="test-key",
        openai_api_key="test-key",
        llm_provider="anthropic",
        postgres_url="postgresql+asyncpg://nexus:test@localhost:5432/nexus_test",
        postgres_url_sync="postgresql://nexus:test@localhost:5432/nexus_test",
        redis_url="redis://localhost:6379/15",
        qdrant_url="http://localhost:6333",
        neo4j_uri="bolt://localhost:7687",
        neo4j_password="test",
        minio_endpoint="localhost:9000",
        minio_access_key="test",
        minio_secret_key="test",
        enable_reranker=False,
        enable_sparse_embeddings=False,
        enable_splade_sparse=False,
        enable_visual_embeddings=False,
        enable_near_duplicate_detection=False,
        enable_coreference_resolution=False,
    )
    defaults.update(overrides)
    return Settings(**defaults)


class TestSPLADEDependency:
    """Verify get_sparse_embedder() SPLADE routing."""

    def test_get_sparse_embedder_returns_splade_when_enabled(self):
        """When ENABLE_SPLADE_SPARSE=true, factory should return SPLADEProvider."""
        from app.dependencies import get_sparse_embedder

        mock_settings = _make_test_settings(enable_splade_sparse=True)
        with (
            patch("app.dependencies.get_settings", return_value=mock_settings),
            patch("app.ingestion.splade_embedder.SPLADEProvider") as mock_cls,
        ):
            sentinel = MagicMock()
            mock_cls.return_value = sentinel

            get_sparse_embedder.cache_clear()
            result = get_sparse_embedder()

            assert result is sentinel
            mock_cls.assert_called_once_with(
                doc_model="naver/splade-v3-doc",
                query_model="naver/splade-v3-query",
                max_length=512,
            )
            get_sparse_embedder.cache_clear()

    def test_get_sparse_embedder_returns_bm42_when_splade_disabled(self):
        """When only ENABLE_SPARSE_EMBEDDINGS=true, factory returns BM42 SparseEmbedder."""
        from app.dependencies import get_sparse_embedder

        mock_settings = _make_test_settings(
            enable_sparse_embeddings=True,
            enable_splade_sparse=False,
        )
        with (
            patch("app.dependencies.get_settings", return_value=mock_settings),
            patch("app.dependencies.SparseEmbedder") as mock_cls,
        ):
            sentinel = MagicMock()
            mock_cls.return_value = sentinel

            get_sparse_embedder.cache_clear()
            result = get_sparse_embedder()

            assert result is sentinel
            mock_cls.assert_called_once()
            get_sparse_embedder.cache_clear()

    def test_get_sparse_embedder_returns_none_when_all_disabled(self):
        """When both sparse flags are off, factory returns None."""
        from app.dependencies import get_sparse_embedder

        mock_settings = _make_test_settings(
            enable_sparse_embeddings=False,
            enable_splade_sparse=False,
        )
        with patch("app.dependencies.get_settings", return_value=mock_settings):
            get_sparse_embedder.cache_clear()
            result = get_sparse_embedder()

            assert result is None
            get_sparse_embedder.cache_clear()
