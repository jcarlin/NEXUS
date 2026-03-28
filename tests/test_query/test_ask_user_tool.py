"""Tests for the ask_user clarification tool and related plumbing.

Covers:
- ask_user tool behaviour (interrupt call, guard logic, resume)
- ClarificationResponse schema validation
- System prompt injection based on enable_agent_clarification flag
- Graph tool list composition
- POST /query/resume route existence
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.query.tools import ask_user

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MATTER_ID = "00000000-0000-0000-0000-000000000001"

_BASE_STATE = {
    "_filters": {"matter_id": _MATTER_ID},
    "_exclude_privilege": ["privileged", "work_product"],
    "_term_map": {},
    "messages": [],
}


def _state_with_prior_asks(n_prior: int) -> dict:
    """Build a state dict containing *n_prior* AIMessages that each carry a
    tool_call with name ``ask_user``.  The tool_calls list uses the LangChain
    dict format recognised by AIMessage.
    """
    messages: list = []
    for i in range(n_prior):
        messages.append(
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": f"call_{i}",
                        "name": "ask_user",
                        "args": {"question": f"Clarification question {i}?"},
                    }
                ],
            )
        )
    return {**_BASE_STATE, "messages": messages}


# ---------------------------------------------------------------------------
# 1. ask_user calls interrupt
# ---------------------------------------------------------------------------


async def test_ask_user_calls_interrupt():
    """ask_user should call langgraph.types.interrupt with the question payload
    and return the user's answer prefixed with 'User clarification:'."""
    with patch("langgraph.types.interrupt", return_value="the CEO") as mock_interrupt:
        result = await ask_user.ainvoke({"question": "Which John Smith — the CEO or the CFO?", "state": _BASE_STATE})

    mock_interrupt.assert_called_once_with({"question": "Which John Smith — the CEO or the CFO?"})
    assert result == "User clarification: the CEO"


# ---------------------------------------------------------------------------
# 2. ask_user blocks second call
# ---------------------------------------------------------------------------


async def test_ask_user_blocks_second_call():
    """When state already contains >1 prior ask_user tool calls the guard
    should fire and return the 'already asked' message without calling
    interrupt."""
    state = _state_with_prior_asks(2)

    with patch("langgraph.types.interrupt") as mock_interrupt:
        result = await ask_user.ainvoke({"question": "Another question?", "state": state})

    mock_interrupt.assert_not_called()
    assert "already asked a clarification question" in result


async def test_ask_user_allows_first_call():
    """When there is 0-1 prior ask_user tool calls in messages the guard
    should NOT block and interrupt should be called normally."""
    # Zero prior asks
    with patch("langgraph.types.interrupt", return_value="yes") as mock_interrupt:
        result = await ask_user.ainvoke({"question": "Is this the right entity?", "state": _BASE_STATE})
    mock_interrupt.assert_called_once()
    assert "User clarification:" in result

    # Exactly one prior ask — guard counts > 1, so one is allowed
    state_one = _state_with_prior_asks(1)
    with patch("langgraph.types.interrupt", return_value="yes") as mock_interrupt:
        result = await ask_user.ainvoke({"question": "Narrow the time range?", "state": state_one})
    mock_interrupt.assert_called_once()
    assert "User clarification:" in result


# ---------------------------------------------------------------------------
# 3. ask_user returns answer on resume
# ---------------------------------------------------------------------------


async def test_ask_user_returns_answer_on_resume():
    """When the graph is resumed, interrupt() returns the user's answer.
    Verify the tool passes it through correctly."""
    with patch("langgraph.types.interrupt", return_value="John Smith the CFO"):
        result = await ask_user.ainvoke({"question": "Which John Smith?", "state": _BASE_STATE})

    assert result == "User clarification: John Smith the CFO"


async def test_ask_user_returns_empty_answer():
    """Edge case: interrupt returns an empty string (user submitted empty)."""
    with patch("langgraph.types.interrupt", return_value=""):
        result = await ask_user.ainvoke({"question": "Which entity?", "state": _BASE_STATE})

    assert result == "User clarification: "


# ---------------------------------------------------------------------------
# 4. ask_user NOT in tools when flag disabled
# ---------------------------------------------------------------------------


def test_ask_user_not_in_tools_when_flag_disabled():
    """When enable_agent_clarification is False the INVESTIGATION_TOOLS list
    should NOT contain ask_user.  The graph build logic conditionally extends
    with CLARIFICATION_TOOLS only when the flag is set."""
    from app.query.tools import CLARIFICATION_TOOLS, INVESTIGATION_TOOLS

    # INVESTIGATION_TOOLS is the *base* list — should never include ask_user
    base_names = [t.name for t in INVESTIGATION_TOOLS]
    assert "ask_user" not in base_names

    # CLARIFICATION_TOOLS is a separate list containing ask_user
    clarification_names = [t.name for t in CLARIFICATION_TOOLS]
    assert "ask_user" in clarification_names


def test_graph_build_includes_ask_user_when_enabled():
    """Simulate the tool list construction in build_agentic_graph to verify
    ask_user is included when the flag is True."""
    from app.query.tools import CLARIFICATION_TOOLS, INVESTIGATION_TOOLS

    tools = list(INVESTIGATION_TOOLS)

    # Simulate enable_agent_clarification=True
    tools.extend(CLARIFICATION_TOOLS)

    tool_names = [t.name for t in tools]
    assert "ask_user" in tool_names
    # All base tools still present
    assert "vector_search" in tool_names
    assert "graph_query" in tool_names


def test_graph_build_excludes_ask_user_when_disabled():
    """Simulate the tool list construction when flag is False — only base
    INVESTIGATION_TOOLS, no CLARIFICATION_TOOLS."""
    from app.query.tools import INVESTIGATION_TOOLS

    tools = list(INVESTIGATION_TOOLS)
    # No extend with CLARIFICATION_TOOLS
    tool_names = [t.name for t in tools]
    assert "ask_user" not in tool_names


# ---------------------------------------------------------------------------
# 5. ClarificationResponse schema validation
# ---------------------------------------------------------------------------


def test_clarification_response_schema_valid():
    """ClarificationResponse should accept a valid thread_id and answer."""
    from app.query.schemas import ClarificationResponse

    cr = ClarificationResponse(
        thread_id=uuid.UUID("12345678-1234-5678-1234-567812345678"),
        answer="John Smith the CFO",
    )
    assert cr.thread_id == uuid.UUID("12345678-1234-5678-1234-567812345678")
    assert cr.answer == "John Smith the CFO"


def test_clarification_response_rejects_empty_answer():
    """Answer must be at least 1 character (min_length=1)."""
    from pydantic import ValidationError

    from app.query.schemas import ClarificationResponse

    with pytest.raises(ValidationError) as exc_info:
        ClarificationResponse(
            thread_id=uuid.UUID("12345678-1234-5678-1234-567812345678"),
            answer="",
        )
    errors = exc_info.value.errors()
    assert any(e["loc"] == ("answer",) for e in errors)


def test_clarification_response_rejects_too_long_answer():
    """Answer must not exceed 4000 characters (max_length=4000)."""
    from pydantic import ValidationError

    from app.query.schemas import ClarificationResponse

    with pytest.raises(ValidationError) as exc_info:
        ClarificationResponse(
            thread_id=uuid.UUID("12345678-1234-5678-1234-567812345678"),
            answer="x" * 4001,
        )
    errors = exc_info.value.errors()
    assert any(e["loc"] == ("answer",) for e in errors)


def test_clarification_response_accepts_max_length_answer():
    """Exactly 4000 chars should be accepted."""
    from app.query.schemas import ClarificationResponse

    cr = ClarificationResponse(
        thread_id=uuid.UUID("12345678-1234-5678-1234-567812345678"),
        answer="x" * 4000,
    )
    assert len(cr.answer) == 4000


def test_clarification_response_rejects_invalid_thread_id():
    """thread_id must be a valid UUID."""
    from pydantic import ValidationError

    from app.query.schemas import ClarificationResponse

    with pytest.raises(ValidationError):
        ClarificationResponse(
            thread_id="not-a-uuid",
            answer="valid answer",
        )


def test_clarification_response_requires_thread_id():
    """thread_id is required (not Optional)."""
    from pydantic import ValidationError

    from app.query.schemas import ClarificationResponse

    with pytest.raises(ValidationError):
        ClarificationResponse(answer="some answer")


# ---------------------------------------------------------------------------
# 6. System prompt includes clarification when enabled
# ---------------------------------------------------------------------------


def test_system_prompt_includes_clarification_when_enabled():
    """When enable_agent_clarification=True, build_system_prompt should append
    the CLARIFICATION_ADDENDUM containing 'ask_user'."""
    from app.query.nodes import build_system_prompt

    state = {
        "_case_context": "",
        "_query_type": "",
        "messages": [HumanMessage(content="Who is John Smith?")],
    }

    mock_settings = MagicMock()
    mock_settings.enable_agent_clarification = True

    with patch("app.dependencies.get_settings", return_value=mock_settings):
        result = build_system_prompt(state)

    # First element is SystemMessage
    system_msg = result[0]
    assert "ask_user" in system_msg.content
    assert "clarification" in system_msg.content.lower()


# ---------------------------------------------------------------------------
# 7. System prompt excludes clarification when disabled
# ---------------------------------------------------------------------------


def test_system_prompt_excludes_clarification_when_disabled():
    """When enable_agent_clarification=False, build_system_prompt should NOT
    contain the clarification addendum."""
    from app.query.nodes import build_system_prompt

    state = {
        "_case_context": "",
        "_query_type": "",
        "messages": [HumanMessage(content="Who is John Smith?")],
    }

    mock_settings = MagicMock()
    mock_settings.enable_agent_clarification = False

    with patch("app.dependencies.get_settings", return_value=mock_settings):
        result = build_system_prompt(state)

    system_msg = result[0]
    assert "ask_user" not in system_msg.content


def test_system_prompt_preserves_messages():
    """build_system_prompt should return [SystemMessage] + state messages."""
    from langchain_core.messages import SystemMessage

    from app.query.nodes import build_system_prompt

    user_msg = HumanMessage(content="Tell me about the deal")
    ai_msg = AIMessage(content="Here is what I found...")
    state = {
        "_case_context": "",
        "_query_type": "",
        "messages": [user_msg, ai_msg],
    }

    mock_settings = MagicMock()
    mock_settings.enable_agent_clarification = False

    with patch("app.dependencies.get_settings", return_value=mock_settings):
        result = build_system_prompt(state)

    assert len(result) == 3  # SystemMessage + 2 messages
    assert isinstance(result[0], SystemMessage)
    assert result[1] is user_msg
    assert result[2] is ai_msg


def test_system_prompt_with_query_type_and_clarification():
    """When both query_type addendum and clarification are active, the system
    prompt should contain both."""
    from app.query.nodes import build_system_prompt

    state = {
        "_case_context": "",
        "_query_type": "analytical",
        "messages": [],
        "original_query": "test query",
    }

    mock_settings = MagicMock()
    mock_settings.enable_agent_clarification = True

    with patch("app.dependencies.get_settings", return_value=mock_settings):
        result = build_system_prompt(state)

    system_text = result[0].content
    assert "ask_user" in system_text
    assert "Analytical" in system_text


# ---------------------------------------------------------------------------
# 8. POST /query/resume route exists
# ---------------------------------------------------------------------------


async def test_resume_endpoint_exists(client, _test_app):
    """POST /api/v1/query/resume should exist and return 422 when the body
    is empty (route exists but payload validation fails)."""
    from app.dependencies import get_query_graph

    _test_app.dependency_overrides[get_query_graph] = lambda: MagicMock()
    response = await client.post("/api/v1/query/resume", json={})
    # 422 = route found, request body failed validation
    assert response.status_code == 422


async def test_resume_endpoint_rejects_missing_thread_id(client, _test_app):
    """POST /query/resume requires thread_id."""
    from app.dependencies import get_query_graph

    _test_app.dependency_overrides[get_query_graph] = lambda: MagicMock()
    response = await client.post(
        "/api/v1/query/resume",
        json={"answer": "John Smith the CFO"},
    )
    assert response.status_code == 422


async def test_resume_endpoint_rejects_missing_answer(client, _test_app):
    """POST /query/resume requires answer."""
    from app.dependencies import get_query_graph

    _test_app.dependency_overrides[get_query_graph] = lambda: MagicMock()
    response = await client.post(
        "/api/v1/query/resume",
        json={"thread_id": str(uuid.uuid4())},
    )
    assert response.status_code == 422


async def test_resume_endpoint_rejects_empty_answer(client, _test_app):
    """POST /query/resume rejects empty answer string (min_length=1)."""
    from app.dependencies import get_query_graph

    _test_app.dependency_overrides[get_query_graph] = lambda: MagicMock()
    response = await client.post(
        "/api/v1/query/resume",
        json={"thread_id": str(uuid.uuid4()), "answer": ""},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# CLARIFICATION_ADDENDUM prompt content
# ---------------------------------------------------------------------------


def test_clarification_addendum_content():
    """Verify CLARIFICATION_ADDENDUM contains expected guidance."""
    from app.query.prompts import CLARIFICATION_ADDENDUM

    assert "ask_user" in CLARIFICATION_ADDENDUM
    assert "ONE" in CLARIFICATION_ADDENDUM  # "at most ONE clarification question"
    assert "ambiguity" in CLARIFICATION_ADDENDUM


def test_clarification_tools_list_length():
    """CLARIFICATION_TOOLS should contain exactly one tool: ask_user."""
    from app.query.tools import CLARIFICATION_TOOLS

    assert len(CLARIFICATION_TOOLS) == 1
    assert CLARIFICATION_TOOLS[0].name == "ask_user"
