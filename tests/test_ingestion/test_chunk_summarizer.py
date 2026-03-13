"""Tests for the chunk summarization module (T2-11)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.ingestion.chunk_summarizer import summarize_chunks
from app.ingestion.chunker import Chunk


def _make_chunk(index: int, text: str) -> Chunk:
    """Create a test Chunk."""
    return Chunk(
        chunk_index=index,
        text=text,
        token_count=len(text.split()),
        metadata={"source_file": "test.pdf"},
    )


def _make_mock_llm(response: str) -> MagicMock:
    """Create a mock LLMClient that returns the given response."""
    llm = MagicMock()
    llm.complete = AsyncMock(return_value=response)
    return llm


class TestSummarizeChunks:
    """Tests for summarize_chunks."""

    @pytest.mark.asyncio
    async def test_basic_chunk_summarization(self):
        """Each chunk should get a chunk_summary in its metadata."""
        llm = _make_mock_llm("This chunk discusses a payment.")

        chunks = [
            _make_chunk(0, "The payment of $2.5 million was made to Acme Corp."),
            _make_chunk(1, "The board authorized the transaction on January 15."),
        ]

        result = await summarize_chunks(chunks, llm, concurrency=2)

        assert len(result) == 2
        assert result[0].metadata["chunk_summary"] == "This chunk discusses a payment."
        assert result[1].metadata["chunk_summary"] == "This chunk discusses a payment."
        assert llm.complete.call_count == 2

    @pytest.mark.asyncio
    async def test_empty_chunks_list(self):
        """Empty list should return immediately."""
        llm = _make_mock_llm("should not be called")

        result = await summarize_chunks([], llm)

        assert result == []
        llm.complete.assert_not_called()

    @pytest.mark.asyncio
    async def test_concurrency_limit(self):
        """Verify concurrency limit is respected."""
        max_concurrent = 0
        current_concurrent = 0

        async def _tracking_complete(*args, **kwargs):
            nonlocal max_concurrent, current_concurrent
            current_concurrent += 1
            max_concurrent = max(max_concurrent, current_concurrent)
            await asyncio.sleep(0.01)
            current_concurrent -= 1
            return "Summary."

        llm = MagicMock()
        llm.complete = _tracking_complete

        chunks = [_make_chunk(i, f"Chunk {i} text.") for i in range(8)]

        await summarize_chunks(chunks, llm, concurrency=2)

        assert max_concurrent <= 2

    @pytest.mark.asyncio
    async def test_llm_failure_graceful(self):
        """LLM error should not crash; chunk gets empty summary."""
        llm = MagicMock()
        llm.complete = AsyncMock(side_effect=RuntimeError("API Error"))

        chunks = [_make_chunk(0, "Some text.")]

        result = await summarize_chunks(chunks, llm)

        assert result[0].metadata["chunk_summary"] == ""

    @pytest.mark.asyncio
    async def test_prompt_contains_chunk_text(self):
        """The prompt should contain the chunk text."""
        llm = _make_mock_llm("Summary of content.")

        chunks = [_make_chunk(0, "The acquisition was finalized on March 1st.")]

        await summarize_chunks(chunks, llm)

        call_args = llm.complete.call_args
        messages = call_args.kwargs.get("messages") or call_args[0][0]
        prompt_text = messages[0]["content"]
        assert "acquisition was finalized" in prompt_text

    @pytest.mark.asyncio
    async def test_long_chunk_text_truncated(self):
        """Chunk text longer than 1000 chars should be truncated in the prompt."""
        llm = _make_mock_llm("Summary.")

        long_text = "word " * 500  # 2500 chars
        chunks = [_make_chunk(0, long_text)]

        await summarize_chunks(chunks, llm)

        call_args = llm.complete.call_args
        messages = call_args.kwargs.get("messages") or call_args[0][0]
        prompt_text = messages[0]["content"]
        # The chunk text portion should be truncated at 1000 chars
        assert len(prompt_text) < 1500  # prompt template + 1000 chars max

    @pytest.mark.asyncio
    async def test_summary_whitespace_stripped(self):
        """Summaries should have whitespace stripped."""
        llm = _make_mock_llm("  Summary with spaces.  \n")

        chunks = [_make_chunk(0, "Some text.")]
        result = await summarize_chunks(chunks, llm)

        assert result[0].metadata["chunk_summary"] == "Summary with spaces."
