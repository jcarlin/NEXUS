"""Tests for VectorStoreClient: collection creation, upsert, and RRF query."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from qdrant_client.models import Distance

from app.common.vector_store import TEXT_COLLECTION, VISUAL_COLLECTION, VectorStoreClient


def _make_settings(enable_sparse: bool = False, enable_visual: bool = False, enable_multi_repr: bool = False):
    """Create a minimal mock Settings."""
    s = MagicMock()
    s.qdrant_url = "http://localhost:6333"
    s.embedding_dimensions = 1024
    s.enable_visual_embeddings = enable_visual
    s.enable_sparse_embeddings = enable_sparse
    s.enable_multi_representation = enable_multi_repr
    return s


@pytest.fixture()
def mock_qdrant_client():
    """Patch QdrantClient so no real connection is made."""
    with patch("app.common.vector_store.QdrantClient") as mock_client_cls:
        mock_instance = MagicMock()
        mock_client_cls.return_value = mock_instance
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

    chunks = [
        {
            "id": "p1",
            "vector": [0.1] * 1024,
            "payload": {"chunk_text": "hello"},
            "sparse_vector": {"indices": [0, 5], "values": [0.9, 0.4]},
        }
    ]

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


# ---------------------------------------------------------------------------
# T2-9: Per-modality RRF prefetch multiplier tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_per_modality_multipliers(mock_qdrant_client):
    """When separate dense/sparse multipliers provided, each prefetch uses its own."""
    mock_qdrant_client.query_points.return_value.points = []

    client = VectorStoreClient(_make_settings(enable_sparse=True))

    await client.query_text(
        vector=[0.1] * 1024,
        limit=10,
        sparse_vector=([0, 5], [0.9, 0.4]),
        dense_prefetch_multiplier=3,
        sparse_prefetch_multiplier=4,
    )

    call_kwargs = mock_qdrant_client.query_points.call_args.kwargs
    prefetches = call_kwargs["prefetch"]
    assert len(prefetches) == 2

    # Dense prefetch: limit = 10 * 3 = 30
    dense_prefetch = prefetches[0]
    assert dense_prefetch.limit == 30

    # Sparse prefetch: limit = 10 * 4 = 40
    sparse_prefetch = prefetches[1]
    assert sparse_prefetch.limit == 40


@pytest.mark.asyncio
async def test_default_multipliers_backward_compatible(mock_qdrant_client):
    """When no per-modality multipliers provided, falls back to shared multiplier."""
    mock_qdrant_client.query_points.return_value.points = []

    client = VectorStoreClient(_make_settings(enable_sparse=True))

    await client.query_text(
        vector=[0.1] * 1024,
        limit=10,
        sparse_vector=([0, 5], [0.9, 0.4]),
        prefetch_multiplier=2,
    )

    call_kwargs = mock_qdrant_client.query_points.call_args.kwargs
    prefetches = call_kwargs["prefetch"]
    # Both should use shared multiplier: 10 * 2 = 20
    assert prefetches[0].limit == 20
    assert prefetches[1].limit == 20


# ---------------------------------------------------------------------------
# document_date range filter tests
# ---------------------------------------------------------------------------


def _extract_must_conditions(call_kwargs: dict) -> list:
    """Pull the flat list of `must` FieldConditions from a query_points call,
    checking both direct query_filter (dense-only path) and prefetch.filter
    (sparse RRF path).
    """
    qf = call_kwargs.get("query_filter")
    if qf is not None:
        return list(qf.must or [])
    prefetches = call_kwargs.get("prefetch") or []
    for p in prefetches:
        if p.filter is not None:
            return list(p.filter.must or [])
    return []


@pytest.mark.asyncio
async def test_query_text_with_date_range_builds_datetime_range(mock_qdrant_client):
    """date_range kwarg must produce a FieldCondition on document_date with DatetimeRange."""
    from datetime import UTC, datetime

    mock_qdrant_client.query_points.return_value.points = []

    client = VectorStoreClient(_make_settings(enable_sparse=False))

    await client.query_text(
        vector=[0.1] * 1024,
        limit=5,
        date_range={
            "gte": "2020-01-01T00:00:00+00:00",
            "lte": "2020-03-31T23:59:59.999999+00:00",
        },
    )

    call_kwargs = mock_qdrant_client.query_points.call_args.kwargs
    conditions = _extract_must_conditions(call_kwargs)
    date_conditions = [c for c in conditions if c.key == "document_date"]
    assert len(date_conditions) == 1
    rng = date_conditions[0].range
    from qdrant_client.models import DatetimeRange

    assert isinstance(rng, DatetimeRange)
    # Pydantic coerces ISO strings to tz-aware datetime objects
    assert rng.gte == datetime(2020, 1, 1, 0, 0, 0, tzinfo=UTC)
    assert rng.lte == datetime(2020, 3, 31, 23, 59, 59, 999999, tzinfo=UTC)


@pytest.mark.asyncio
async def test_query_text_without_date_range_no_date_condition(mock_qdrant_client):
    """Omitting date_range must not inject any document_date FieldCondition."""
    mock_qdrant_client.query_points.return_value.points = []

    client = VectorStoreClient(_make_settings(enable_sparse=False))

    await client.query_text(vector=[0.1] * 1024, limit=5)

    call_kwargs = mock_qdrant_client.query_points.call_args.kwargs
    conditions = _extract_must_conditions(call_kwargs)
    assert not any(c.key == "document_date" for c in conditions)


@pytest.mark.asyncio
async def test_query_text_date_range_combined_with_filters(mock_qdrant_client):
    """date_range and filters together should produce BOTH conditions in must."""
    mock_qdrant_client.query_points.return_value.points = []

    client = VectorStoreClient(_make_settings(enable_sparse=False))

    await client.query_text(
        vector=[0.1] * 1024,
        limit=5,
        filters={"matter_id": "m-1"},
        date_range={"gte": "2020-01-01T00:00:00+00:00"},
    )

    call_kwargs = mock_qdrant_client.query_points.call_args.kwargs
    conditions = _extract_must_conditions(call_kwargs)
    keys = [c.key for c in conditions]
    assert "matter_id" in keys
    assert "document_date" in keys


@pytest.mark.asyncio
async def test_mixed_multipliers(mock_qdrant_client):
    """When only one per-modality multiplier provided, the other falls back."""
    mock_qdrant_client.query_points.return_value.points = []

    client = VectorStoreClient(_make_settings(enable_sparse=True))

    # Only provide dense_prefetch_multiplier, sparse falls back to prefetch_multiplier
    await client.query_text(
        vector=[0.1] * 1024,
        limit=10,
        sparse_vector=([0, 5], [0.9, 0.4]),
        prefetch_multiplier=2,
        dense_prefetch_multiplier=4,
    )

    call_kwargs = mock_qdrant_client.query_points.call_args.kwargs
    prefetches = call_kwargs["prefetch"]
    # Dense: 10 * 4 = 40
    assert prefetches[0].limit == 40
    # Sparse: falls back to prefetch_multiplier: 10 * 2 = 20
    assert prefetches[1].limit == 20


# ---------------------------------------------------------------------------
# Visual collection tests
# ---------------------------------------------------------------------------


def test_ensure_visual_collection_uses_multivector(mock_qdrant_client):
    """When visual enabled, nexus_visual uses MultiVectorConfig with MAX_SIM."""
    mock_qdrant_client.get_collections.return_value.collections = []

    client = VectorStoreClient(_make_settings(enable_visual=True))
    import asyncio

    asyncio.run(client.ensure_collections())

    # Should create both text and visual collections
    calls = mock_qdrant_client.create_collection.call_args_list
    assert len(calls) == 2

    visual_call = calls[1].kwargs
    assert visual_call["collection_name"] == VISUAL_COLLECTION

    from qdrant_client.models import MultiVectorComparator, VectorParams

    vectors_config = visual_call["vectors_config"]
    assert isinstance(vectors_config, VectorParams)
    assert vectors_config.size == 128
    assert vectors_config.multivector_config is not None
    assert vectors_config.multivector_config.comparator == MultiVectorComparator.MAX_SIM


@pytest.mark.asyncio
async def test_upsert_visual_pages(mock_qdrant_client):
    """upsert_visual_pages should upsert multi-vector points to nexus_visual."""
    client = VectorStoreClient(_make_settings(enable_visual=True))

    pages = [
        {
            "id": "job1_page_1",
            "vectors": [[0.1] * 128, [0.2] * 128],  # 2 patches × 128d
            "payload": {"doc_id": "job1", "page_number": 1},
        }
    ]

    await client.upsert_visual_pages(pages)

    call_args = mock_qdrant_client.upsert.call_args
    assert call_args.kwargs["collection_name"] == VISUAL_COLLECTION
    point = call_args.kwargs["points"][0]
    assert point.id == "job1_page_1"
    assert len(point.vector) == 2  # 2 patches
    assert len(point.vector[0]) == 128


@pytest.mark.asyncio
async def test_query_visual(mock_qdrant_client):
    """query_visual should query nexus_visual with multi-vector query."""
    mock_point = MagicMock()
    mock_point.id = "job1_page_1"
    mock_point.score = 0.85
    mock_point.payload = {"doc_id": "job1", "page_number": 1}
    mock_qdrant_client.query_points.return_value.points = [mock_point]

    client = VectorStoreClient(_make_settings(enable_visual=True))

    results = await client.query_visual(
        query_vectors=[[0.1] * 128, [0.2] * 128],
        limit=5,
        filters={"doc_id": "job1"},
    )

    call_kwargs = mock_qdrant_client.query_points.call_args.kwargs
    assert call_kwargs["collection_name"] == VISUAL_COLLECTION
    assert len(results) == 1
    assert results[0]["doc_id"] == "job1"
    assert results[0]["score"] == 0.85


# ---------------------------------------------------------------------------
# Multi-representation indexing tests
# ---------------------------------------------------------------------------


def test_ensure_collections_multi_repr_creates_summary_vector(mock_qdrant_client):
    """When multi_repr enabled, collection includes 'summary' named vector."""
    mock_qdrant_client.get_collections.return_value.collections = []

    client = VectorStoreClient(_make_settings(enable_multi_repr=True))
    import asyncio

    asyncio.run(client.ensure_collections())

    call_kwargs = mock_qdrant_client.create_collection.call_args_list[0].kwargs
    assert call_kwargs["collection_name"] == TEXT_COLLECTION
    # Named config is a dict with both dense and summary
    assert isinstance(call_kwargs["vectors_config"], dict)
    assert "dense" in call_kwargs["vectors_config"]
    assert "summary" in call_kwargs["vectors_config"]

    from qdrant_client.models import VectorParams

    summary_config = call_kwargs["vectors_config"]["summary"]
    assert isinstance(summary_config, VectorParams)
    assert summary_config.size == 1024
    assert summary_config.distance == Distance.COSINE


@pytest.mark.asyncio
async def test_upsert_with_summary_vector(mock_qdrant_client):
    """When multi_repr enabled, upsert includes summary vector in named format."""
    client = VectorStoreClient(_make_settings(enable_multi_repr=True))

    chunks = [
        {
            "id": "p1",
            "vector": [0.1] * 1024,
            "payload": {"chunk_text": "hello"},
            "summary_vector": [0.2] * 1024,
        }
    ]

    await client.upsert_text_chunks(chunks)

    call_args = mock_qdrant_client.upsert.call_args
    point = call_args.kwargs["points"][0]
    assert isinstance(point.vector, dict)
    assert "dense" in point.vector
    assert "summary" in point.vector
    assert len(point.vector["summary"]) == 1024


@pytest.mark.asyncio
async def test_upsert_multi_repr_without_summary_vector(mock_qdrant_client):
    """When multi_repr enabled but chunk lacks summary_vector, only dense is set."""
    client = VectorStoreClient(_make_settings(enable_multi_repr=True))

    chunks = [
        {
            "id": "p1",
            "vector": [0.1] * 1024,
            "payload": {"chunk_text": "hello"},
        }
    ]

    await client.upsert_text_chunks(chunks)

    call_args = mock_qdrant_client.upsert.call_args
    point = call_args.kwargs["points"][0]
    assert isinstance(point.vector, dict)
    assert "dense" in point.vector
    assert "summary" not in point.vector


@pytest.mark.asyncio
async def test_query_multi_repr_dense_only_uses_rrf(mock_qdrant_client):
    """When multi_repr enabled (no sparse), query uses RRF between dense + summary."""
    mock_qdrant_client.query_points.return_value.points = []

    client = VectorStoreClient(_make_settings(enable_multi_repr=True))

    await client.query_text(
        vector=[0.1] * 1024,
        limit=10,
    )

    call_kwargs = mock_qdrant_client.query_points.call_args.kwargs
    assert "prefetch" in call_kwargs
    assert len(call_kwargs["prefetch"]) == 2  # dense + summary

    from qdrant_client.models import FusionQuery

    assert isinstance(call_kwargs["query"], FusionQuery)

    # Verify the using fields
    prefetch_usings = [p.using for p in call_kwargs["prefetch"]]
    assert "dense" in prefetch_usings
    assert "summary" in prefetch_usings


@pytest.mark.asyncio
async def test_query_triple_rrf_with_sparse_and_multi_repr(mock_qdrant_client):
    """When both sparse and multi_repr enabled, query uses triple RRF fusion."""
    mock_qdrant_client.query_points.return_value.points = []

    client = VectorStoreClient(_make_settings(enable_sparse=True, enable_multi_repr=True))

    await client.query_text(
        vector=[0.1] * 1024,
        limit=10,
        sparse_vector=([0, 5], [0.9, 0.4]),
    )

    call_kwargs = mock_qdrant_client.query_points.call_args.kwargs
    assert "prefetch" in call_kwargs
    assert len(call_kwargs["prefetch"]) == 3  # dense + sparse + summary

    from qdrant_client.models import FusionQuery

    assert isinstance(call_kwargs["query"], FusionQuery)

    # Verify all three vector types in prefetch
    prefetch_usings = [p.using for p in call_kwargs["prefetch"]]
    assert "dense" in prefetch_usings
    assert "sparse" in prefetch_usings
    assert "summary" in prefetch_usings


@pytest.mark.asyncio
async def test_query_multi_repr_disabled_no_summary_prefetch(mock_qdrant_client):
    """When multi_repr disabled, query does NOT include summary prefetch."""
    mock_qdrant_client.query_points.return_value.points = []

    client = VectorStoreClient(_make_settings(enable_sparse=True, enable_multi_repr=False))

    await client.query_text(
        vector=[0.1] * 1024,
        limit=10,
        sparse_vector=([0, 5], [0.9, 0.4]),
    )

    call_kwargs = mock_qdrant_client.query_points.call_args.kwargs
    assert "prefetch" in call_kwargs
    assert len(call_kwargs["prefetch"]) == 2  # dense + sparse only

    prefetch_usings = [p.using for p in call_kwargs["prefetch"]]
    assert "dense" in prefetch_usings
    assert "sparse" in prefetch_usings
    assert "summary" not in prefetch_usings
