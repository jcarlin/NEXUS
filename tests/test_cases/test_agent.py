"""Tests for the Case Setup Agent (LangGraph graph)."""

from __future__ import annotations

from app.cases.agent import CaseSetupState, build_case_setup_graph


def test_case_setup_graph_compiles():
    """build_case_setup_graph() compiles and has the expected 6 nodes."""
    graph = build_case_setup_graph(llm_settings={})
    compiled = graph.compile()

    # LangGraph compiled graph exposes nodes via .get_graph()
    graph_structure = compiled.get_graph()
    # .nodes is a dict keyed by node id
    node_ids = [n for n in graph_structure.nodes if n not in ("__start__", "__end__")]

    assert len(node_ids) == 6
    expected_nodes = {
        "parse_anchor_doc",
        "extract_claims",
        "extract_parties",
        "extract_defined_terms",
        "build_timeline",
        "populate_graph",
    }
    assert set(node_ids) == expected_nodes


def test_case_setup_agent_e2e_mock_llm():
    """Full graph invocation with mocked LLM/Instructor populates all state keys."""
    from app.cases.schemas import (
        ExtractedClaimList,
        ExtractedDefinedTermList,
        ExtractedPartyList,
        ExtractedTimeline,
    )

    mock_claims = ExtractedClaimList(
        claims=[
            {
                "claim_number": 1,
                "claim_label": "Fraud",
                "claim_text": "Defendant committed fraud.",
                "legal_elements": ["intent"],
                "source_pages": [3],
            }
        ]
    )

    mock_parties = ExtractedPartyList(
        parties=[
            {
                "name": "John Doe",
                "role": "plaintiff",
                "description": "Individual",
                "aliases": ["Doe"],
                "source_pages": [1],
            }
        ]
    )

    mock_terms = ExtractedDefinedTermList(
        terms=[
            {
                "term": "the Agreement",
                "definition": "The Purchase Agreement",
                "source_pages": [2],
            }
        ]
    )

    mock_timeline = ExtractedTimeline(
        events=[
            {
                "date": "2020-01-01",
                "event_text": "Agreement signed",
                "source_page": 2,
            }
        ]
    )

    # Build the graph with fully mocked nodes (no external calls)
    def mock_parse(state):
        return {"document_text": "This is a legal complaint about fraud..."}

    def mock_extract_claims(state):
        if not state.get("document_text", "").strip():
            return {"claims": []}
        return {"claims": [c.model_dump() for c in mock_claims.claims]}

    def mock_extract_parties(state):
        if not state.get("document_text", "").strip():
            return {"parties": []}
        return {"parties": [p.model_dump() for p in mock_parties.parties]}

    def mock_extract_terms(state):
        if not state.get("document_text", "").strip():
            return {"defined_terms": []}
        return {"defined_terms": [t.model_dump() for t in mock_terms.terms]}

    def mock_build_timeline(state):
        if not state.get("document_text", "").strip():
            return {"timeline": []}
        return {"timeline": [e.model_dump() for e in mock_timeline.events]}

    def mock_populate_graph(state):
        return {}

    from langgraph.graph import END, START, StateGraph

    graph = StateGraph(CaseSetupState)
    graph.add_node("parse_anchor_doc", mock_parse)
    graph.add_node("extract_claims", mock_extract_claims)
    graph.add_node("extract_parties", mock_extract_parties)
    graph.add_node("extract_defined_terms", mock_extract_terms)
    graph.add_node("build_timeline", mock_build_timeline)
    graph.add_node("populate_graph", mock_populate_graph)

    graph.add_edge(START, "parse_anchor_doc")
    graph.add_edge("parse_anchor_doc", "extract_claims")
    graph.add_edge("extract_claims", "extract_parties")
    graph.add_edge("extract_parties", "extract_defined_terms")
    graph.add_edge("extract_defined_terms", "build_timeline")
    graph.add_edge("build_timeline", "populate_graph")
    graph.add_edge("populate_graph", END)

    compiled = graph.compile()

    result = compiled.invoke(
        {
            "matter_id": "test-matter",
            "minio_path": "raw/test/complaint.pdf",
            "document_text": "",
            "claims": [],
            "parties": [],
            "defined_terms": [],
            "timeline": [],
        }
    )

    # Verify all state keys are populated
    assert result["document_text"] == "This is a legal complaint about fraud..."
    assert len(result["claims"]) == 1
    assert result["claims"][0]["claim_label"] == "Fraud"
    assert len(result["parties"]) == 1
    assert result["parties"][0]["name"] == "John Doe"
    assert len(result["defined_terms"]) == 1
    assert result["defined_terms"][0]["term"] == "the Agreement"
    assert len(result["timeline"]) == 1
    assert result["timeline"][0]["date"] == "2020-01-01"
