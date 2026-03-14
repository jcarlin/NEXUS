"""Tests for document text comparison (T3-4).

Covers ``compute_text_diff`` and ``extract_document_text`` from
``app.documents.comparison``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.documents.comparison import MAX_DIFF_CHARS, compute_text_diff, extract_document_text

# ---------------------------------------------------------------------------
# compute_text_diff
# ---------------------------------------------------------------------------


class TestComputeTextDiff:
    """Unit tests for compute_text_diff."""

    def test_identical_texts(self) -> None:
        text = "line one\nline two\nline three\n"
        blocks, truncated = compute_text_diff(text, text)
        assert not truncated
        assert len(blocks) == 1
        assert blocks[0]["op"] == "equal"
        assert blocks[0]["left_text"] == text
        assert blocks[0]["right_text"] == text

    def test_simple_insert(self) -> None:
        text_a = "line one\nline three\n"
        text_b = "line one\nline two\nline three\n"
        blocks, truncated = compute_text_diff(text_a, text_b)
        assert not truncated
        ops = [b["op"] for b in blocks]
        assert "insert" in ops
        # Inserted line should appear in right_text of the insert block
        insert_block = next(b for b in blocks if b["op"] == "insert")
        assert "line two" in insert_block["right_text"]
        assert insert_block["left_text"] == ""

    def test_simple_delete(self) -> None:
        text_a = "line one\nline two\nline three\n"
        text_b = "line one\nline three\n"
        blocks, truncated = compute_text_diff(text_a, text_b)
        assert not truncated
        ops = [b["op"] for b in blocks]
        assert "delete" in ops
        delete_block = next(b for b in blocks if b["op"] == "delete")
        assert "line two" in delete_block["left_text"]
        assert delete_block["right_text"] == ""

    def test_replace_block(self) -> None:
        text_a = "line one\noriginal line\nline three\n"
        text_b = "line one\nreplaced line\nline three\n"
        blocks, truncated = compute_text_diff(text_a, text_b)
        assert not truncated
        ops = [b["op"] for b in blocks]
        assert "replace" in ops
        replace_block = next(b for b in blocks if b["op"] == "replace")
        assert "original" in replace_block["left_text"]
        assert "replaced" in replace_block["right_text"]

    def test_mixed_changes(self) -> None:
        text_a = "alpha\nbeta\ngamma\ndelta\n"
        text_b = "alpha\nBETA\ngamma\ndelta\nepsilon\n"
        blocks, truncated = compute_text_diff(text_a, text_b)
        assert not truncated
        ops = [b["op"] for b in blocks]
        assert "equal" in ops
        # beta -> BETA is a replace; epsilon is an insert
        assert "replace" in ops or "insert" in ops

    def test_empty_left(self) -> None:
        blocks, truncated = compute_text_diff("", "hello\n")
        assert not truncated
        assert len(blocks) == 1
        assert blocks[0]["op"] == "insert"
        assert blocks[0]["left_text"] == ""
        assert "hello" in blocks[0]["right_text"]

    def test_empty_right(self) -> None:
        blocks, truncated = compute_text_diff("hello\n", "")
        assert not truncated
        assert len(blocks) == 1
        assert blocks[0]["op"] == "delete"
        assert "hello" in blocks[0]["left_text"]
        assert blocks[0]["right_text"] == ""

    def test_both_empty(self) -> None:
        blocks, truncated = compute_text_diff("", "")
        assert not truncated
        assert len(blocks) == 0

    def test_truncates_long_text(self) -> None:
        long_text = "x" * (MAX_DIFF_CHARS + 1000)
        short_text = "y\n"
        blocks, truncated = compute_text_diff(long_text, short_text)
        assert truncated
        # Should still produce valid blocks despite truncation
        assert isinstance(blocks, list)

    def test_line_numbers_consistent(self) -> None:
        text_a = "a\nb\nc\nd\n"
        text_b = "a\nB\nc\nd\n"
        blocks, _ = compute_text_diff(text_a, text_b)
        for block in blocks:
            assert block["left_start"] is not None
            assert block["left_end"] is not None
            assert block["right_start"] is not None
            assert block["right_end"] is not None
            assert block["left_start"] <= block["left_end"]
            assert block["right_start"] <= block["right_end"]

    def test_multiline_replace(self) -> None:
        text_a = "header\nold line 1\nold line 2\nfooter\n"
        text_b = "header\nnew line 1\nnew line 2\nnew line 3\nfooter\n"
        blocks, truncated = compute_text_diff(text_a, text_b)
        assert not truncated
        replace_block = next(b for b in blocks if b["op"] == "replace")
        assert "old line" in replace_block["left_text"]
        assert "new line" in replace_block["right_text"]


# ---------------------------------------------------------------------------
# extract_document_text
# ---------------------------------------------------------------------------


class TestExtractDocumentText:
    """Unit tests for extract_document_text."""

    @pytest.mark.asyncio
    async def test_success_markdown(self) -> None:
        storage = AsyncMock()
        storage.download_bytes = AsyncMock(return_value=b"# Document Title\n\nSome text.")
        result = await extract_document_text("job-123", "report.pdf", storage)
        assert result == "# Document Title\n\nSome text."
        storage.download_bytes.assert_called_once_with("parsed/job-123/report.md")

    @pytest.mark.asyncio
    async def test_fallback_to_txt(self) -> None:
        storage = AsyncMock()
        storage.download_bytes = AsyncMock(side_effect=[Exception("not found"), b"Plain text content."])
        result = await extract_document_text("job-456", "memo.docx", storage)
        assert result == "Plain text content."
        assert storage.download_bytes.call_count == 2

    @pytest.mark.asyncio
    async def test_not_found(self) -> None:
        storage = AsyncMock()
        storage.download_bytes = AsyncMock(side_effect=Exception("not found"))
        with pytest.raises(FileNotFoundError, match="No parsed text found"):
            await extract_document_text("job-789", "missing.pdf", storage)

    @pytest.mark.asyncio
    async def test_empty_content(self) -> None:
        storage = AsyncMock()
        storage.download_bytes = AsyncMock(return_value=b"")
        result = await extract_document_text("job-000", "empty.pdf", storage)
        assert result == ""
