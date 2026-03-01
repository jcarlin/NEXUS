"""Tests for the TextEmbedder (mocked OpenAI API)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ingestion.embedder import TextEmbedder


@pytest.mark.asyncio
async def test_embed_query_returns_vector():
    """embed_query should return a list of floats."""
    embedder = TextEmbedder(api_key="test-key", dimensions=1024)

    mock_data = MagicMock()
    mock_data.index = 0
    mock_data.embedding = [0.1] * 1024

    mock_response = MagicMock()
    mock_response.data = [mock_data]

    with patch.object(embedder._client.embeddings, "create", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = mock_response
        result = await embedder.embed_query("test text")

    assert len(result) == 1024
    assert all(isinstance(x, float) for x in result)


@pytest.mark.asyncio
async def test_embed_texts_batching():
    """embed_texts should batch requests when over BATCH_SIZE."""
    embedder = TextEmbedder(api_key="test-key", dimensions=4, batch_size=2)

    def make_response(count, offset=0):
        resp = MagicMock()
        resp.data = [MagicMock(index=i, embedding=[float(i + offset)] * 4) for i in range(count)]
        return resp

    with patch.object(embedder._client.embeddings, "create", new_callable=AsyncMock) as mock_create:
        mock_create.side_effect = [make_response(2, 0), make_response(1, 2)]
        results = await embedder.embed_texts(["a", "b", "c"])

    assert len(results) == 3
    assert mock_create.call_count == 2  # Two batches


@pytest.mark.asyncio
async def test_embed_empty_raises():
    embedder = TextEmbedder(api_key="test-key")
    with pytest.raises(ValueError, match="empty"):
        await embedder.embed_texts([])
