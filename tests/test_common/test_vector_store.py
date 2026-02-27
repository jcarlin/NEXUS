"""Tests for VectorStoreClient: collection creation, upsert, and RRF query."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.common.vector_store import TEXT_COLLECTION, VectorStoreClient


def _make_settings(enable_sparse: bool = False):
    """Create a minimal mock Settings."""
    s = MagicMock()
    s.qdrant_url = "http://localhost:6333"
    s.embedding_dimensions = 1024
    s.enable_visual_embeddings = False
    s.enable_sparse_embeddings = enable_sparse
    return s


@pytest.fixture()
def mock_qdrant_client():
    """Patch QdrantClient so no real connection is made."""
    with patch("app.common.vector_store.QdrantClient") as MockClient:
        mock_instance = MagicMock()
        MockClient.return_value = mock_instance
        yield mock_instance


def test_ensure_collections_dense_only(mock_qdrant_client):
    """When sparse disabled, collection uses unnamed VectorParams."""
    mock_qdrant_client.get_collections.return_value.collections = []

    client = VectorStoreClient(_make_settings(enable_sparse=False))
    import asyncio
    asyncio.run(client.ensure_collections())

    call_kwargs = mock_qdrant_client.create_collection.call_args_list[0].kwargs
    assert call_kwargs["collection_name"] == TEXT_COLLECTION
    # Unnamed config is a VectorParams, not a dict
    from qdrant_client.models import VectorParams
    assert isinstance(call_kwargs["vectors_config"], VectorParams)
    assert "sparse_vectors_config" not in call_kwargs


def test_ensure_collections_named_sparse(mock_qdrant_client):
    """When sparse enabled, collection uses named vectors + sparse config."""
    mock_qdrant_client.get_collections.return_value.collections = []

    client = VectorStoreClient(_make_settings(enable_sparse=True))
    import asyncio
    asyncio.run(client.ensure_collections())

    call_kwargs = mock_qdrant_client.create_collection.call_args_list[0].kwargs
    assert call_kwargs["collection_name"] == TEXT_COLLECTION
    # Named config is a dict
    assert isinstance(call_kwargs["vectors_config"], dict)
    assert "dense" in call_kwargs["vectors_config"]
    assert "sparse_vectors_config" in call_kwargs
    assert "sparse" in call_kwargs["sparse_vectors_config"]


@pytest.mark.asyncio
async def test_upsert_with_named_vectors(mock_qdrant_client):
    """When sparse enabled, upsert uses named vector format."""
    client = VectorStoreClient(_make_settings(enable_sparse=True))

    chunks = [{
        "id": "p1",
        "vector": [0.1] * 1024,
        "payload": {"chunk_text": "hello"},
        "sparse_vector": {"indices": [0, 5], "values": [0.9, 0.4]},
    }]

    await client.upsert_text_chunks(chunks)

    call_args = mock_qdrant_client.upsert.call_args
    point = call_args.kwargs["points"][0]
    assert isinstance(point.vector, dict)
    assert "dense" in point.vector
    assert "sparse" in point.vector


@pytest.mark.asyncio
async def test_query_with_rrf_fusion(mock_qdrant_client):
    """When sparse vector provided + enabled, query uses prefetch + FusionQuery."""
    mock_qdrant_client.query_points.return_value.points = []

    client = VectorStoreClient(_make_settings(enable_sparse=True))

    await client.query_text(
        vector=[0.1] * 1024,
        limit=10,
        sparse_vector=([0, 5], [0.9, 0.4]),
    )

    call_kwargs = mock_qdrant_client.query_points.call_args.kwargs
    assert "prefetch" in call_kwargs
    assert len(call_kwargs["prefetch"]) == 2
    from qdrant_client.models import FusionQuery
    assert isinstance(call_kwargs["query"], FusionQuery)
