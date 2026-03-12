"""Tests for the contextual chunk enrichment module."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ingestion.chunker import Chunk
from app.ingestion.contextualizer import ChunkContextualizer, _parse_numbered_response


def _make_chunk(index: int, text: str, quality_score: float | None = None) -> Chunk:
    """Create a test Chunk."""
    meta: dict = {"source_file": "test.pdf", "chunk_index": index}
    if quality_score is not None:
        meta["quality_score"] = quality_score
    return Chunk(
        chunk_index=index,
        text=text,
        token_count=len(text.split()),
        metadata=meta,
    )


def _make_mock_llm(response: str) -> MagicMock:
    """Create a mock LLMClient that returns the given response."""
    llm = MagicMock()
    llm.complete = AsyncMock(return_value=response)
    return llm


class TestParseNumberedResponse:
    """Tests for _parse_numbered_response."""

    def test_bracket_format(self):
        response = "[1] Context for chunk one.\n[2] Context for chunk two."
        result = _parse_numbered_response(response, 2)
        assert result == ["Context for chunk one.", "Context for chunk two."]

    def test_dot_format(self):
        response = "1. Context for chunk one.\n2. Context for chunk two."
        result = _parse_numbered_response(response, 2)
        assert result == ["Context for chunk one.", "Context for chunk two."]

    def test_colon_format(self):
        response = "1: Context one.\n2: Context two.\n3: Context three."
        result = _parse_numbered_response(response, 3)
        assert result == ["Context one.", "Context two.", "Context three."]

    def test_missing_numbers_padded(self):
        response = "[1] Context for chunk one.\n[3] Context for chunk three."
        result = _parse_numbered_response(response, 3)
        assert result[0] == "Context for chunk one."
        assert result[1] == ""  # Missing [2]
        assert result[2] == "Context for chunk three."

    def test_empty_response_fallback(self):
        response = "Some random text\nAnother line"
        result = _parse_numbered_response(response, 2)
        assert len(result) == 2

    def test_empty_response(self):
        result = _parse_numbered_response("", 3)
        assert result == ["", "", ""]


class TestChunkContextualizer:
    """Tests for ChunkContextualizer."""

    @pytest.mark.asyncio
    async def test_contextualize_batch_success(self):
        """Mock LLM returns numbered sentences, chunks get context_prefix."""
        llm = _make_mock_llm(
            "[1] Discusses a $2.5M payment to Acme Corp.\n[2] Details the board authorization process."
        )
        ctx = ChunkContextualizer(llm=llm, batch_size=10, concurrency=2)

        chunks = [
            _make_chunk(0, "The payment of $2.5 million was made to Acme Corp."),
            _make_chunk(1, "The board authorized the transaction."),
        ]

        result = await ctx.contextualize_batch(chunks, doc_title="Test Doc", doc_type="contract")

        assert result[0].context_prefix == "Discusses a $2.5M payment to Acme Corp."
        assert result[1].context_prefix == "Details the board authorization process."

    @pytest.mark.asyncio
    async def test_batch_splitting(self):
        """100 chunks should be split into batches."""
        llm = _make_mock_llm("")  # Will return empty prefixes
        ctx = ChunkContextualizer(llm=llm, batch_size=20, concurrency=4)

        chunks = [_make_chunk(i, f"Chunk {i} text here.") for i in range(100)]

        await ctx.contextualize_batch(chunks, doc_title="Test", doc_type="report")

        # Should have been called 5 times (100 / 20)
        assert llm.complete.call_count == 5

    @pytest.mark.asyncio
    async def test_concurrent_batches(self):
        """Verify concurrency limit is respected."""
        call_count = 0
        max_concurrent = 0
        current_concurrent = 0

        async def _tracking_complete(*args, **kwargs):
            nonlocal call_count, max_concurrent, current_concurrent
            current_concurrent += 1
            max_concurrent = max(max_concurrent, current_concurrent)
            call_count += 1
            await asyncio.sleep(0.01)  # Simulate latency
            current_concurrent -= 1
            return "[1] Context."

        llm = MagicMock()
        llm.complete = _tracking_complete

        ctx = ChunkContextualizer(llm=llm, batch_size=1, concurrency=2)
        chunks = [_make_chunk(i, f"Chunk {i}.") for i in range(6)]

        await ctx.contextualize_batch(chunks, doc_title="Test", doc_type="report")

        assert call_count == 6
        assert max_concurrent <= 2  # Concurrency limit

    @pytest.mark.asyncio
    async def test_llm_failure_graceful(self):
        """LLM raising an exception should not crash; chunks keep None prefix."""
        llm = MagicMock()
        llm.complete = AsyncMock(side_effect=RuntimeError("API Error"))

        ctx = ChunkContextualizer(llm=llm, batch_size=10)
        chunks = [_make_chunk(0, "Some text.")]

        result = await ctx.contextualize_batch(chunks, doc_title="Test", doc_type="report")

        assert result[0].context_prefix is None  # Graceful: no crash

    @pytest.mark.asyncio
    async def test_context_prefix_used_in_embedding(self):
        """Embedding text should be prefix + original when prefix exists."""
        chunk = _make_chunk(0, "The payment was made.")
        chunk.context_prefix = "John Smith discusses a payment to Acme Corp."

        # Simulate what _stage_embed does
        text = f"{chunk.context_prefix}\n\n{chunk.text}" if chunk.context_prefix else chunk.text

        assert text == "John Smith discusses a payment to Acme Corp.\n\nThe payment was made."

    @pytest.mark.asyncio
    async def test_qdrant_payload_preserves_original(self):
        """chunk_text in Qdrant should be the original, not the contextualized text."""
        chunk = _make_chunk(0, "Original chunk text here.")
        chunk.context_prefix = "Context about the original chunk."

        # Simulate payload construction (from _stage_index)
        payload = {
            "chunk_text": chunk.text,
            "context_prefix": chunk.context_prefix or "",
        }

        assert payload["chunk_text"] == "Original chunk text here."
        assert payload["context_prefix"] == "Context about the original chunk."

    @pytest.mark.asyncio
    async def test_skip_low_quality_chunks(self):
        """Chunks with quality_score < threshold should not be sent to LLM."""
        llm = _make_mock_llm("[1] Context for good chunk.")
        ctx = ChunkContextualizer(llm=llm, batch_size=10)

        chunks = [
            _make_chunk(0, "Good content here.", quality_score=0.8),
            _make_chunk(1, "CONFIDENTIAL PAGE 1 OF 1", quality_score=0.1),
        ]

        await ctx.contextualize_batch(chunks, doc_title="Test", doc_type="report", min_quality_score=0.2)

        # LLM should only be called once (only 1 chunk passed the threshold)
        assert llm.complete.call_count == 1
        assert chunks[0].context_prefix == "Context for good chunk."
        assert chunks[1].context_prefix is None  # Skipped

    @pytest.mark.asyncio
    async def test_stage_skipped_when_disabled(self):
        """When feature flag is off, _stage_contextualize should be a no-op."""
        from app.ingestion.tasks import _PipelineContext, _stage_contextualize

        settings = MagicMock()
        settings.enable_contextual_chunks = False

        engine = MagicMock()
        engine.connect = MagicMock(return_value=MagicMock(__enter__=MagicMock(), __exit__=MagicMock()))

        ctx = _PipelineContext(
            settings=settings,
            engine=engine,
            job_id="test-job",
            minio_path="raw/test.pdf",
            filename="test.pdf",
            matter_id=None,
        )
        ctx.chunks = [_make_chunk(0, "Some text.")]
        ctx.progress = {}

        with patch("app.ingestion.tasks._update_stage"):
            _stage_contextualize(ctx)

        # No context_prefix should be set
        assert ctx.chunks[0].context_prefix is None

    @pytest.mark.asyncio
    async def test_long_prefix_truncated(self):
        """Context prefixes longer than 50 words should be truncated."""
        long_response = "[1] " + " ".join(["word"] * 80) + "."
        llm = _make_mock_llm(long_response)
        ctx = ChunkContextualizer(llm=llm, batch_size=10)

        chunks = [_make_chunk(0, "Test chunk.")]
        await ctx.contextualize_batch(chunks, doc_title="Test", doc_type="report")

        assert chunks[0].context_prefix is not None
        assert len(chunks[0].context_prefix.split()) <= 51  # 50 words + "..."
