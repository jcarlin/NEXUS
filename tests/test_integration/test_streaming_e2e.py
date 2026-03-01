"""Integration tests: SSE streaming end-to-end.

Tests the streaming event flow (status, sources, token, done) by
invoking the compiled LangGraph with ``astream()``.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _base_state(query: str = "Who is John Doe?") -> dict:
    return {
        "messages": [],
        "thread_id": "test-thread",
        "user_id": "test-user",
        "original_query": query,
        "rewritten_query": "",
        "query_type": "",
        "text_results": [],
        "visual_results": [],
        "graph_results": [],
        "fused_context": [],
        "response": "",
        "source_documents": [],
        "follow_up_questions": [],
        "entities_mentioned": [],
        "_relevance": "",
        "_reformulated": False,
        "_filters": None,
    }


async def _collect_stream_events(graph, state: dict) -> list[tuple[str, dict]]:
    """Run graph.astream and collect all (stream_mode, chunk) tuples."""
    events = []
    config = {"configurable": {"thread_id": "test-stream"}}
    async for stream_mode, chunk in graph.astream(state, config, stream_mode=["updates", "custom"]):
        events.append((stream_mode, chunk))
    return events


def _extract_sse_events(raw_events: list[tuple[str, dict]]) -> list[dict]:
    """Convert raw stream events into SSE-like event dicts for easier testing."""
    sse = []
    for mode, chunk in raw_events:
        if mode == "updates":
            for node_name, update in chunk.items():
                sse.append({"event": "status", "node": node_name})
                if node_name == "rerank" and "source_documents" in update:
                    sse.append({"event": "sources", "documents": update["source_documents"]})
        elif mode == "custom":
            if isinstance(chunk, dict) and chunk.get("type") == "token":
                sse.append({"event": "token", "text": chunk["text"]})
    # Final done event (simulated — in real router this is appended after stream)
    sse.append({"event": "done"})
    return sse


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_stream_full_pipeline_emits_all_event_types(compiled_graph, mock_services):
    """Stream should emit status, sources, token, and done events."""
    mock_services["llm"].complete.side_effect = [
        "factual",
        "Who is John Doe?",
        "Follow-up one\nFollow-up two\nFollow-up three",
    ]

    state = _base_state()
    raw_events = await _collect_stream_events(compiled_graph, state)
    sse = _extract_sse_events(raw_events)

    event_types = {e["event"] for e in sse}
    assert "status" in event_types
    assert "sources" in event_types
    assert "token" in event_types
    assert "done" in event_types


async def test_stream_sources_before_tokens(compiled_graph, mock_services):
    """Sources event must appear before the first token event."""
    mock_services["llm"].complete.side_effect = [
        "factual",
        "Who is John Doe?",
        "Follow-up one\nFollow-up two\nFollow-up three",
    ]

    state = _base_state()
    raw_events = await _collect_stream_events(compiled_graph, state)
    sse = _extract_sse_events(raw_events)

    sources_idx = None
    first_token_idx = None
    for i, e in enumerate(sse):
        if e["event"] == "sources" and sources_idx is None:
            sources_idx = i
        if e["event"] == "token" and first_token_idx is None:
            first_token_idx = i

    assert sources_idx is not None, "No sources event found"
    assert first_token_idx is not None, "No token event found"
    assert sources_idx < first_token_idx, "Sources must arrive before tokens"


async def test_stream_done_contains_thread_and_followups(compiled_graph, mock_services):
    """The final state should contain thread_id and follow_up_questions."""
    mock_services["llm"].complete.side_effect = [
        "factual",
        "Who is John Doe?",
        "What connections does John Doe have?\nAre there financial records?\nWhat is the timeline?",
    ]

    state = _base_state()
    config = {"configurable": {"thread_id": "test-stream-done"}}

    final_state = await compiled_graph.ainvoke(state, config)

    assert final_state["thread_id"] == "test-thread"
    assert isinstance(final_state["follow_up_questions"], list)
    assert len(final_state["follow_up_questions"]) <= 3


async def test_stream_saves_to_database(compiled_graph, mock_services):
    """Verify that the router's _save_message would be called correctly.

    We test the pattern used by the router: accumulate final_state from
    stream events, then verify it has the expected structure for DB save.
    """
    mock_services["llm"].complete.side_effect = [
        "factual",
        "Who is John Doe?",
        "Follow-up one\nFollow-up two\nFollow-up three",
    ]

    state = _base_state()
    raw_events = await _collect_stream_events(compiled_graph, state)

    # Simulate how the router accumulates final_state
    final_state: dict = {}
    for mode, chunk in raw_events:
        if mode == "updates":
            for node_name, update in chunk.items():
                final_state.update(update)

    # The final_state should have all fields needed for _save_message
    assert "response" in final_state
    assert "source_documents" in final_state
    assert "entities_mentioned" in final_state
    assert "follow_up_questions" in final_state


async def test_stream_handles_empty_retrieval(mock_services):
    """Stream should complete normally even with no retrieval results."""
    from app.query.graph import build_graph

    mock_services["retriever"].retrieve_all.return_value = ([], [])
    # Empty retrieval triggers: classify, rewrite, reformulate, follow-ups (4 calls)
    # The reformulation path adds an extra LLM call
    mock_services["llm"].complete.side_effect = [
        "factual",  # classify
        "Who is John Doe?",  # rewrite
        "alternative query about John Doe",  # reformulate
        "Follow-up one\nFollow-up two\nFollow-up three",  # follow-ups
    ]
    mock_services["entity_extractor"].extract.return_value = []

    graph = build_graph(
        llm=mock_services["llm"],
        retriever=mock_services["retriever"],
        graph_service=mock_services["graph_service"],
        entity_extractor=mock_services["entity_extractor"],
    ).compile()

    state = _base_state()
    raw_events = await _collect_stream_events(graph, state)
    sse = _extract_sse_events(raw_events)

    # Should still have status and done events even with empty results
    event_types = {e["event"] for e in sse}
    assert "status" in event_types
    assert "done" in event_types
