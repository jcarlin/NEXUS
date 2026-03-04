"""Tests for _extract_text_from_content and QueryService.extract_response."""

from __future__ import annotations

from app.query.service import QueryService, _extract_text_from_content


class TestExtractTextFromContent:
    """Unit tests for the content block extraction helper."""

    def test_string_passthrough(self):
        assert _extract_text_from_content("Hello world") == "Hello world"

    def test_empty_string(self):
        assert _extract_text_from_content("") == ""

    def test_single_text_block(self):
        content = [{"type": "text", "text": "The answer is 42."}]
        assert _extract_text_from_content(content) == "The answer is 42."

    def test_multi_block_list(self):
        content = [
            {"type": "text", "text": "First part. "},
            {"type": "text", "text": "Second part."},
        ]
        assert _extract_text_from_content(content) == "First part. Second part."

    def test_mixed_types_in_list(self):
        content = [
            {"type": "text", "text": "Hello "},
            {"type": "tool_use", "id": "call_1", "name": "search"},
            {"type": "text", "text": "world"},
        ]
        assert _extract_text_from_content(content) == "Hello world"

    def test_string_items_in_list(self):
        content = ["Just a string"]
        assert _extract_text_from_content(content) == "Just a string"

    def test_empty_list(self):
        assert _extract_text_from_content([]) == ""

    def test_non_string_non_list_fallback(self):
        assert _extract_text_from_content(42) == "42"  # type: ignore[arg-type]

    def test_block_without_text_key(self):
        content = [{"type": "text"}]
        assert _extract_text_from_content(content) == ""

    def test_mixed_string_and_dict_blocks(self):
        content = [
            "prefix ",
            {"type": "text", "text": "suffix"},
        ]
        assert _extract_text_from_content(content) == "prefix suffix"


class TestExtractResponse:
    """Tests for QueryService.extract_response with content block handling."""

    def test_response_field_takes_priority(self):
        state = {"response": "Direct response", "messages": []}
        assert QueryService.extract_response(state, is_agentic=True) == "Direct response"

    def test_agentic_string_content(self):
        from langchain_core.messages import AIMessage

        state = {"response": "", "messages": [AIMessage(content="The answer.")]}
        assert QueryService.extract_response(state, is_agentic=True) == "The answer."

    def test_agentic_list_content(self):
        from langchain_core.messages import AIMessage

        msg = AIMessage(content=[{"type": "text", "text": "Block answer."}])
        state = {"response": "", "messages": [msg]}
        assert QueryService.extract_response(state, is_agentic=True) == "Block answer."

    def test_agentic_multi_block_content(self):
        from langchain_core.messages import AIMessage

        msg = AIMessage(
            content=[
                {"type": "text", "text": "Part 1. "},
                {"type": "text", "text": "Part 2."},
            ]
        )
        state = {"response": "", "messages": [msg]}
        assert QueryService.extract_response(state, is_agentic=True) == "Part 1. Part 2."

    def test_agentic_dict_message_with_list_content(self):
        state = {
            "response": "",
            "messages": [
                {"role": "assistant", "content": [{"type": "text", "text": "Dict msg."}]},
            ],
        }
        assert QueryService.extract_response(state, is_agentic=True) == "Dict msg."

    def test_empty_messages(self):
        state = {"response": "", "messages": []}
        assert QueryService.extract_response(state, is_agentic=True) == ""

    def test_v1_uses_response_field(self):
        state = {"response": "V1 answer"}
        assert QueryService.extract_response(state, is_agentic=False) == "V1 answer"
