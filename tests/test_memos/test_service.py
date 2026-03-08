"""Tests for MemoService."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.memos.schemas import MemoFormat
from app.memos.service import MemoService

# ---------------------------------------------------------------------------
# _parse_sections
# ---------------------------------------------------------------------------


class TestParseSections:
    """Unit tests for MemoService._parse_sections."""

    def test_parse_markdown_headings(self) -> None:
        """Markdown with ## headings is split into separate MemoSection objects."""
        content = (
            "## Executive Summary\n"
            "This is the summary.\n"
            "\n"
            "## Factual Findings\n"
            "Finding one.\n"
            "Finding two.\n"
            "\n"
            "## Conclusion\n"
            "The conclusion.\n"
        )
        sections = MemoService._parse_sections(content)

        assert len(sections) == 3
        assert sections[0].heading == "Executive Summary"
        assert "summary" in sections[0].content.lower()
        assert sections[1].heading == "Factual Findings"
        assert "Finding one" in sections[1].content
        assert sections[2].heading == "Conclusion"

    def test_parse_h1_headings(self) -> None:
        """# headings are also parsed."""
        content = "# Header\nSome content.\n"
        sections = MemoService._parse_sections(content)

        assert len(sections) == 1
        assert sections[0].heading == "Header"
        assert "Some content" in sections[0].content

    def test_no_headings_wraps_as_single_section(self) -> None:
        """Content without headings is wrapped as a single Memorandum section."""
        content = "Just plain text without any heading markers.\nSecond line."
        sections = MemoService._parse_sections(content)

        assert len(sections) == 1
        assert sections[0].heading == "Memorandum"
        assert "plain text" in sections[0].content

    def test_empty_sections_skipped(self) -> None:
        """Sections with heading but no content are skipped."""
        content = "## Empty Section\n## Has Content\nSome content here."
        sections = MemoService._parse_sections(content)

        # The empty section has no content lines, so only the one with content is kept
        assert len(sections) == 1
        assert sections[0].heading == "Has Content"

    def test_strips_content_whitespace(self) -> None:
        """Section content has leading/trailing whitespace stripped."""
        content = "## Title\n\n   Some content   \n\n"
        sections = MemoService._parse_sections(content)

        assert sections[0].content == "Some content"


# ---------------------------------------------------------------------------
# generate_memo
# ---------------------------------------------------------------------------


class TestGenerateMemo:
    """Tests for MemoService.generate_memo with mocked LLM and DB."""

    @pytest.mark.asyncio
    async def test_generate_memo_with_query(self) -> None:
        """generate_memo calls LLM and persists the result."""
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=MagicMock())

        mock_llm = AsyncMock()
        # First call: title generation, second call: memo content
        mock_llm.complete = AsyncMock(
            side_effect=[
                "Financial Investigation Memo",
                "## Executive Summary\nKey findings.\n\n## Conclusion\nDone.",
            ]
        )

        result = await MemoService.generate_memo(
            db=mock_db,
            matter_id=uuid4(),
            user_id=uuid4(),
            llm=mock_llm,
            query="What financial transactions occurred?",
        )

        assert result.title == "Financial Investigation Memo"
        assert len(result.sections) == 2
        assert result.sections[0].heading == "Executive Summary"
        assert result.format == MemoFormat.MARKDOWN
        # LLM called twice: once for title, once for content
        assert mock_llm.complete.call_count == 2
        # DB execute called once for INSERT
        assert mock_db.execute.call_count == 1

    @pytest.mark.asyncio
    async def test_generate_memo_with_custom_title(self) -> None:
        """When title is provided, LLM is called only once for content."""
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=MagicMock())

        mock_llm = AsyncMock()
        mock_llm.complete = AsyncMock(return_value="## Summary\nContent here.")

        result = await MemoService.generate_memo(
            db=mock_db,
            matter_id=uuid4(),
            user_id=uuid4(),
            llm=mock_llm,
            query="Test query",
            title="Custom Title",
        )

        assert result.title == "Custom Title"
        # LLM called only once (for content, no title generation)
        assert mock_llm.complete.call_count == 1

    @pytest.mark.asyncio
    async def test_generate_memo_with_thread_id(self) -> None:
        """generate_memo gathers context from thread when thread_id is provided."""
        # Mock DB: first call = gather thread context, second = get thread query, third = INSERT
        mock_thread_rows = []
        mock_query_row = MagicMock()
        mock_query_row._mapping = {"content": "Who is involved?"}
        mock_query_result = MagicMock()
        mock_query_result.first.return_value = mock_query_row
        mock_context_result = MagicMock()
        mock_context_result.all.return_value = mock_thread_rows
        mock_insert_result = MagicMock()

        call_count = 0

        async def mock_execute(stmt, params=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_context_result  # _gather_thread_context
            if call_count == 2:
                return mock_query_result  # _get_thread_query
            return mock_insert_result  # INSERT

        mock_db = AsyncMock()
        mock_db.execute = mock_execute

        mock_llm = AsyncMock()
        mock_llm.complete = AsyncMock(side_effect=["Thread Memo Title", "## Summary\nThread content."])

        result = await MemoService.generate_memo(
            db=mock_db,
            matter_id=uuid4(),
            user_id=uuid4(),
            llm=mock_llm,
            thread_id="thread-123",
        )

        assert result.thread_id == "thread-123"
        assert result.title == "Thread Memo Title"

    @pytest.mark.asyncio
    async def test_generate_memo_requires_thread_or_query(self) -> None:
        """generate_memo raises ValueError when neither thread_id nor query is given."""
        mock_db = AsyncMock()
        mock_llm = AsyncMock()

        with pytest.raises(ValueError, match="Either thread_id or query"):
            await MemoService.generate_memo(
                db=mock_db,
                matter_id=uuid4(),
                user_id=uuid4(),
                llm=mock_llm,
            )


# ---------------------------------------------------------------------------
# list_memos
# ---------------------------------------------------------------------------


class TestListMemos:
    """Tests for MemoService.list_memos."""

    @pytest.mark.asyncio
    async def test_list_memos_returns_paginated(self) -> None:
        """list_memos returns (items, total) tuple."""
        matter_id = uuid4()
        memo_id = uuid4()
        user_id = uuid4()
        now = datetime.now(UTC)

        # Mock count result
        mock_count = MagicMock()
        mock_count.scalar.return_value = 1

        # Mock rows result
        mock_row = MagicMock()
        mock_row._mapping = {
            "id": memo_id,
            "matter_id": matter_id,
            "thread_id": None,
            "title": "Test Memo",
            "sections": [{"heading": "Summary", "content": "Test", "citations": []}],
            "format": "markdown",
            "created_by": user_id,
            "created_at": now,
        }
        mock_result = MagicMock()
        mock_result.all.return_value = [mock_row]

        call_count = 0

        async def mock_execute(stmt, params=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_count
            return mock_result

        mock_db = AsyncMock()
        mock_db.execute = mock_execute

        memos, total = await MemoService.list_memos(mock_db, matter_id)

        assert total == 1
        assert len(memos) == 1
        assert memos[0].title == "Test Memo"
        assert memos[0].id == memo_id


# ---------------------------------------------------------------------------
# get_memo
# ---------------------------------------------------------------------------


class TestGetMemo:
    """Tests for MemoService.get_memo."""

    @pytest.mark.asyncio
    async def test_get_memo_not_found(self) -> None:
        """get_memo returns None when memo does not exist."""
        mock_result = MagicMock()
        mock_result.first.return_value = None

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await MemoService.get_memo(mock_db, uuid4(), uuid4())

        assert result is None

    @pytest.mark.asyncio
    async def test_get_memo_found(self) -> None:
        """get_memo returns MemoResponse when memo exists."""
        memo_id = uuid4()
        matter_id = uuid4()
        now = datetime.now(UTC)

        mock_row = MagicMock()
        mock_row._mapping = {
            "id": memo_id,
            "matter_id": matter_id,
            "thread_id": "thread-1",
            "title": "Found Memo",
            "sections": [{"heading": "S1", "content": "C1", "citations": []}],
            "format": "markdown",
            "created_by": uuid4(),
            "created_at": now,
        }
        mock_result = MagicMock()
        mock_result.first.return_value = mock_row

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await MemoService.get_memo(mock_db, memo_id, matter_id)

        assert result is not None
        assert result.id == memo_id
        assert result.title == "Found Memo"
        assert result.thread_id == "thread-1"


# ---------------------------------------------------------------------------
# delete_memo
# ---------------------------------------------------------------------------


class TestDeleteMemo:
    """Tests for MemoService.delete_memo."""

    @pytest.mark.asyncio
    async def test_delete_memo_not_found(self) -> None:
        """delete_memo returns False when memo does not exist."""
        mock_result = MagicMock()
        mock_result.rowcount = 0

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await MemoService.delete_memo(mock_db, uuid4(), uuid4())

        assert result is False

    @pytest.mark.asyncio
    async def test_delete_memo_success(self) -> None:
        """delete_memo returns True when memo is deleted."""
        mock_result = MagicMock()
        mock_result.rowcount = 1

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await MemoService.delete_memo(mock_db, uuid4(), uuid4())

        assert result is True
