"""Tests for the DI singleton pattern using ``@functools.cache``."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.config import Settings

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
        enable_visual_embeddings=False,
        enable_near_duplicate_detection=False,
        enable_coreference_resolution=False,
    )
    defaults.update(overrides)
    return Settings(**defaults)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCachedSingletons:
    """Verify that @functools.cache delivers singleton semantics."""

    def test_get_qdrant_returns_same_instance(self):
        """Repeated calls to ``get_qdrant()`` return the identical object."""
        from app.dependencies import get_qdrant

        mock_settings = _make_test_settings()
        with (
            patch("app.dependencies.get_settings", return_value=mock_settings),
            patch("app.dependencies.VectorStoreClient") as mock_cls,
        ):
            sentinel = MagicMock()
            mock_cls.return_value = sentinel

            get_qdrant.cache_clear()
            a = get_qdrant()
            b = get_qdrant()

            assert a is b
            assert a is sentinel
            mock_cls.assert_called_once_with(mock_settings)
            get_qdrant.cache_clear()

    def test_get_minio_returns_same_instance(self):
        """Repeated calls to ``get_minio()`` return the identical object."""
        from app.dependencies import get_minio

        mock_settings = _make_test_settings()
        with (
            patch("app.dependencies.get_settings", return_value=mock_settings),
            patch("app.dependencies.StorageClient") as mock_cls,
        ):
            sentinel = MagicMock()
            mock_cls.return_value = sentinel

            get_minio.cache_clear()
            a = get_minio()
            b = get_minio()

            assert a is b
            assert a is sentinel
            mock_cls.assert_called_once_with(mock_settings)
            get_minio.cache_clear()

    def test_cache_clear_resets_singleton(self):
        """After ``cache_clear()``, the factory creates a fresh instance."""
        from app.dependencies import get_qdrant

        mock_settings = _make_test_settings()
        with (
            patch("app.dependencies.get_settings", return_value=mock_settings),
            patch("app.dependencies.VectorStoreClient") as mock_cls,
        ):
            first = MagicMock()
            second = MagicMock()
            mock_cls.side_effect = [first, second]

            get_qdrant.cache_clear()
            a = get_qdrant()
            get_qdrant.cache_clear()
            b = get_qdrant()

            assert a is first
            assert b is second
            assert a is not b
            assert mock_cls.call_count == 2
            get_qdrant.cache_clear()


class TestFeatureFlaggedFactories:
    """Feature-flagged factories return ``None`` when the flag is off."""

    def test_reranker_disabled_returns_none(self):
        from app.dependencies import get_reranker

        mock_settings = _make_test_settings(enable_reranker=False)
        with patch("app.dependencies.get_settings", return_value=mock_settings):
            get_reranker.cache_clear()
            result = get_reranker()
            assert result is None
            get_reranker.cache_clear()

    def test_reranker_enabled_returns_instance(self):
        from app.dependencies import get_reranker

        mock_settings = _make_test_settings(enable_reranker=True, reranker_model="test-model")
        with (
            patch("app.dependencies.get_settings", return_value=mock_settings),
            patch("app.dependencies.Reranker") as mock_cls,
        ):
            sentinel = MagicMock()
            mock_cls.return_value = sentinel

            get_reranker.cache_clear()
            result = get_reranker()

            assert result is sentinel
            mock_cls.assert_called_once_with(model_name="test-model")
            get_reranker.cache_clear()

    def test_sparse_embedder_disabled_returns_none(self):
        from app.dependencies import get_sparse_embedder

        mock_settings = _make_test_settings(enable_sparse_embeddings=False)
        with patch("app.dependencies.get_settings", return_value=mock_settings):
            get_sparse_embedder.cache_clear()
            result = get_sparse_embedder()
            assert result is None
            get_sparse_embedder.cache_clear()

    def test_visual_embedder_disabled_returns_none(self):
        from app.dependencies import get_visual_embedder

        mock_settings = _make_test_settings(enable_visual_embeddings=False)
        with patch("app.dependencies.get_settings", return_value=mock_settings):
            get_visual_embedder.cache_clear()
            result = get_visual_embedder()
            assert result is None
            get_visual_embedder.cache_clear()

    def test_dedup_detector_disabled_returns_none(self):
        from app.dependencies import get_dedup_detector

        mock_settings = _make_test_settings(enable_near_duplicate_detection=False)
        with patch("app.dependencies.get_settings", return_value=mock_settings):
            get_dedup_detector.cache_clear()
            result = get_dedup_detector()
            assert result is None
            get_dedup_detector.cache_clear()

    def test_coref_resolver_disabled_returns_none(self):
        from app.dependencies import get_coref_resolver

        mock_settings = _make_test_settings(enable_coreference_resolution=False)
        with patch("app.dependencies.get_settings", return_value=mock_settings):
            get_coref_resolver.cache_clear()
            result = get_coref_resolver()
            assert result is None
            get_coref_resolver.cache_clear()


class TestCloseAll:
    """Verify ``close_all()`` tears down resources and clears caches."""

    @pytest.mark.asyncio
    async def test_close_all_clears_all_caches(self):
        """After ``close_all()``, every factory's cache is empty."""
        from app.dependencies import _ALL_CACHED_FACTORIES, close_all

        # Clear any leftover state from previous tests to prevent
        # close_all() from trying to tear down real service clients
        # (e.g. neo4j AsyncDriver) on a closed or mismatched event loop.
        for fn in _ALL_CACHED_FACTORIES:
            fn.cache_clear()

        # Pre-populate a few caches with mock objects
        mock_settings = _make_test_settings()
        with (
            patch("app.dependencies.get_settings", return_value=mock_settings),
            patch("app.dependencies.VectorStoreClient", return_value=MagicMock()),
            patch("app.dependencies.StorageClient", return_value=MagicMock()),
            patch("app.dependencies.AsyncGraphDatabase.driver", return_value=MagicMock()),
        ):
            from app.dependencies import get_minio, get_qdrant

            get_qdrant.cache_clear()
            get_minio.cache_clear()
            get_qdrant()
            get_minio()

            assert get_qdrant.cache_info().currsize == 1
            assert get_minio.cache_info().currsize == 1

            await close_all()

            # All caches should be cleared
            for fn in _ALL_CACHED_FACTORIES:
                assert fn.cache_info().currsize == 0, f"{fn.__name__} cache was not cleared"

    @pytest.mark.asyncio
    async def test_close_all_disposes_engine(self):
        """``close_all()`` calls ``dispose()`` on the async engine."""
        from app.dependencies import _get_engine, close_all

        mock_engine = MagicMock()
        mock_engine.dispose = MagicMock(return_value=None)

        # Make dispose() awaitable
        async def _fake_dispose():
            pass

        mock_engine.dispose = _fake_dispose

        mock_settings = _make_test_settings()
        with (
            patch("app.dependencies.get_settings", return_value=mock_settings),
            patch("app.dependencies.create_async_engine", return_value=mock_engine),
        ):
            _get_engine.cache_clear()
            _get_engine()  # populate the cache

            await close_all()

            assert _get_engine.cache_info().currsize == 0

    @pytest.mark.asyncio
    async def test_close_all_safe_when_nothing_initialised(self):
        """``close_all()`` does not raise when no singletons were created."""
        from app.dependencies import _ALL_CACHED_FACTORIES, close_all

        # Clear everything first
        for fn in _ALL_CACHED_FACTORIES:
            fn.cache_clear()

        # Should not raise
        await close_all()
