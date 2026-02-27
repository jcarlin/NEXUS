"""Shared fixtures for integration tests.

These tests exercise multi-module interactions (ingest→query, streaming,
error recovery) using real function calls with mocked external services.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.query.graph import build_graph


@dataclass
class FakeEntity:
    """Minimal entity stand-in for tests."""

    text: str
    type: str
    score: float
    start: int
    end: int


@pytest.fixture()
def mock_services() -> dict:
    """Return a dict of mocked service dependencies for the query graph."""
    llm = AsyncMock()
    llm.complete.return_value = "factual"

    async def _mock_stream(messages, **kwargs):
        yield "Generated answer with [Source: doc.pdf, page 1]."

    llm.stream = _mock_stream

    retriever = AsyncMock()
    retriever.retrieve_all.return_value = (
        [
            {
                "id": "c1",
                "score": 0.9,
                "source_file": "doc.pdf",
                "page_number": 1,
                "chunk_text": "Key evidence from the document.",
            },
            {
                "id": "c2",
                "score": 0.7,
                "source_file": "doc2.pdf",
                "page_number": 3,
                "chunk_text": "Supporting evidence from another document.",
            },
        ],
        [
            {
                "source": "Person A",
                "relationship_type": "ASSOCIATED_WITH",
                "target": "Org B",
            },
        ],
    )

    graph_service = AsyncMock()
    graph_service.get_entity_connections.return_value = []

    entity_extractor = MagicMock()
    entity_extractor.extract.return_value = [
        FakeEntity(text="John Doe", type="person", score=0.9, start=0, end=8),
    ]

    return {
        "llm": llm,
        "retriever": retriever,
        "graph_service": graph_service,
        "entity_extractor": entity_extractor,
    }


@pytest.fixture()
def compiled_graph(mock_services: dict):
    """Return a compiled LangGraph using real build_graph with mocked deps."""
    graph = build_graph(
        llm=mock_services["llm"],
        retriever=mock_services["retriever"],
        graph_service=mock_services["graph_service"],
        entity_extractor=mock_services["entity_extractor"],
    )
    return graph.compile()
