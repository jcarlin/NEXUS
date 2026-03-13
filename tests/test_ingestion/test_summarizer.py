"""Tests for the document summarization module (T2-12)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ingestion.chunker import Chunk
from app.ingestion.summarizer import _MAX_CONTENT_CHARS, summarize_document


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


class TestSummarizeDocument:
    """Tests for summarize_document."""

    @pytest.mark.asyncio
    async def test_basic_summary_generation(self):
        """LLM should be called with chunk texts and filename."""
        expected = "This is a contract between Party A and Party B regarding a real estate transaction."
        llm = _make_mock_llm(expected)

        chunks = [
            _make_chunk(0, "AGREEMENT entered into between Party A and Party B."),
            _make_chunk(1, "This contract concerns the sale of property at 123 Main St."),
        ]

        result = await summarize_document(chunks, llm, "contract.pdf")

        assert result == expected
        llm.complete.assert_called_once()
        call_args = llm.complete.call_args
        messages = call_args.kwargs.get("messages") or call_args[0][0]
        prompt_text = messages[0]["content"]
        assert "contract.pdf" in prompt_text
        assert "Party A" in prompt_text

    @pytest.mark.asyncio
    async def test_empty_chunks_returns_empty(self):
        """No chunks should return an empty string without calling LLM."""
        llm = _make_mock_llm("should not be called")

        result = await summarize_document([], llm, "empty.pdf")

        assert result == ""
        llm.complete.assert_not_called()

    @pytest.mark.asyncio
    async def test_chunk_truncation_for_large_documents(self):
        """Large documents should truncate content at the character limit."""
        llm = _make_mock_llm("Summary of large document.")

        # Create chunks that exceed the max content chars
        large_text = "x" * 5000
        chunks = [_make_chunk(i, large_text) for i in range(5)]

        result = await summarize_document(chunks, llm, "large.pdf")

        assert result == "Summary of large document."
        call_args = llm.complete.call_args
        messages = call_args.kwargs.get("messages") or call_args[0][0]
        prompt_text = messages[0]["content"]
        # The content portion should not exceed the max
        # (the prompt includes filename + template text too)
        content_lines = prompt_text.split("Content:\n")[-1]
        assert len(content_lines) <= _MAX_CONTENT_CHARS + 500  # Allow for partial inclusion + "..."

    @pytest.mark.asyncio
    async def test_summary_whitespace_stripped(self):
        """Summary should have leading/trailing whitespace stripped."""
        llm = _make_mock_llm("  Summary with spaces.  \n\n")

        chunks = [_make_chunk(0, "Some text.")]
        result = await summarize_document(chunks, llm, "test.pdf")

        assert result == "Summary with spaces."

    @pytest.mark.asyncio
    async def test_llm_called_with_correct_params(self):
        """LLM should be called with max_tokens=200, temperature=0.0."""
        llm = _make_mock_llm("Summary.")

        chunks = [_make_chunk(0, "Test content.")]
        await summarize_document(chunks, llm, "test.pdf")

        call_kwargs = llm.complete.call_args.kwargs
        assert call_kwargs["max_tokens"] == 200
        assert call_kwargs["temperature"] == 0.0
        assert call_kwargs["node_name"] == "document_summarizer"


class TestFeatureFlagGating:
    """Test that document summarization is gated by feature flag."""

    def test_stage_skipped_when_disabled(self):
        """When feature flag is off, _stage_summarize should be a no-op for doc summary."""
        from app.ingestion.tasks import _PipelineContext, _stage_summarize

        settings = MagicMock()
        settings.enable_document_summarization = False
        settings.enable_multi_representation = False

        engine = MagicMock()
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

        _stage_summarize(ctx)

        assert ctx.document_summary == ""

    def test_stage_runs_when_enabled(self):
        """When feature flag is on, _stage_summarize should generate summary."""
        from app.ingestion.tasks import _PipelineContext, _stage_summarize

        settings = MagicMock()
        settings.enable_document_summarization = True
        settings.enable_multi_representation = False
        settings.llm_provider = "anthropic"
        settings.llm_model = "test-model"
        settings.anthropic_api_key = "test-key"

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
        ctx.chunks = [_make_chunk(0, "Important legal content here.")]
        ctx.progress = {}

        with (
            patch("app.llm_config.resolver.resolve_llm_config_sync", side_effect=Exception("no DB")),
            patch("app.common.llm.LLMClient"),
            patch("app.ingestion.tasks.asyncio.run") as mock_run,
        ):
            mock_run.return_value = "Generated summary."
            _stage_summarize(ctx)

        assert ctx.document_summary == "Generated summary."
        assert ctx.progress.get("document_summary_generated") is True
