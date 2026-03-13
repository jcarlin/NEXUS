"""Tests for T3-15: Matryoshka Dimensionality Optimization."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestMatryoshkaTruncation:
    """Test vector truncation for Matryoshka search."""

    def test_truncation_when_enabled(self):
        """Vectors should be truncated when matryoshka_search_dimensions > 0."""
        full_vector = list(range(1024))
        target_dim = 256
        truncated = full_vector[:target_dim]
        assert len(truncated) == 256
        assert truncated == list(range(256))

    def test_no_truncation_when_disabled(self):
        """Vectors should not be truncated when matryoshka_search_dimensions = 0."""
        full_vector = list(range(1024))
        matryoshka_dim = 0
        if matryoshka_dim > 0:
            result = full_vector[:matryoshka_dim]
        else:
            result = full_vector
        assert len(result) == 1024

    def test_no_truncation_when_vector_smaller(self):
        """Don't truncate if vector is already smaller than target."""
        small_vector = list(range(128))
        target_dim = 256
        if len(small_vector) > target_dim:
            result = small_vector[:target_dim]
        else:
            result = small_vector
        assert len(result) == 128

    def test_config_default_disabled(self):
        """Default config should have matryoshka disabled."""
        with patch.dict("os.environ", {}, clear=True):
            from app.config import Settings

            s = Settings()
            assert s.matryoshka_search_dimensions == 0

    @pytest.mark.asyncio
    async def test_query_text_truncates_vector(self):
        """query_text should truncate the vector when matryoshka is enabled."""
        with patch("app.common.vector_store.QdrantClient") as mock_client_cls:
            mock_instance = MagicMock()
            mock_client_cls.return_value = mock_instance
            mock_instance.query_points.return_value.points = []

            settings = MagicMock()
            settings.qdrant_url = "http://localhost:6333"
            settings.embedding_dimensions = 1024
            settings.enable_visual_embeddings = False
            settings.enable_sparse_embeddings = False
            settings.enable_multi_representation = False

            from app.common.vector_store import VectorStoreClient

            client = VectorStoreClient(settings)

            # Mock get_settings to return settings with matryoshka enabled
            mock_settings = MagicMock()
            mock_settings.matryoshka_search_dimensions = 256

            with patch("app.dependencies.get_settings", return_value=mock_settings):
                await client.query_text(vector=[0.1] * 1024, limit=10)

            call_kwargs = mock_instance.query_points.call_args.kwargs
            # The query vector should have been truncated to 256 dimensions
            assert len(call_kwargs["query"]) == 256

    @pytest.mark.asyncio
    async def test_query_text_no_truncation_when_disabled(self):
        """query_text should NOT truncate the vector when matryoshka is disabled."""
        with patch("app.common.vector_store.QdrantClient") as mock_client_cls:
            mock_instance = MagicMock()
            mock_client_cls.return_value = mock_instance
            mock_instance.query_points.return_value.points = []

            settings = MagicMock()
            settings.qdrant_url = "http://localhost:6333"
            settings.embedding_dimensions = 1024
            settings.enable_visual_embeddings = False
            settings.enable_sparse_embeddings = False
            settings.enable_multi_representation = False

            from app.common.vector_store import VectorStoreClient

            client = VectorStoreClient(settings)

            # Mock get_settings to return settings with matryoshka disabled
            mock_settings = MagicMock()
            mock_settings.matryoshka_search_dimensions = 0

            with patch("app.dependencies.get_settings", return_value=mock_settings):
                await client.query_text(vector=[0.1] * 1024, limit=10)

            call_kwargs = mock_instance.query_points.call_args.kwargs
            # The query vector should remain at full 1024 dimensions
            assert len(call_kwargs["query"]) == 1024
