"""Tests for DepositionService."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.depositions.schemas import QuestionCategory, WitnessProfile
from app.depositions.service import DepositionService, _parse_questions

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MATTER_ID = uuid4()


def _mock_graph_service(
    *,
    entity: dict | None = None,
    connections: list[dict] | None = None,
    run_query_result: list[dict] | None = None,
) -> AsyncMock:
    """Create a mock GraphService with configurable return values."""
    gs = AsyncMock()
    gs.get_entity_by_name = AsyncMock(return_value=entity)
    gs.get_entity_connections = AsyncMock(return_value=connections or [])
    gs._run_query = AsyncMock(return_value=run_query_result or [])
    return gs


def _mock_db(*, doc_rows: list[dict] | None = None) -> AsyncMock:
    """Create a mock AsyncSession with configurable execute results."""
    db = AsyncMock()
    rows = []
    for row_data in doc_rows or []:
        mock_row = MagicMock()
        mock_row._mapping = row_data
        rows.append(mock_row)
    mock_result = MagicMock()
    mock_result.all.return_value = rows
    db.execute = AsyncMock(return_value=mock_result)
    return db


# ---------------------------------------------------------------------------
# list_witnesses
# ---------------------------------------------------------------------------


class TestListWitnesses:
    """Tests for DepositionService.list_witnesses."""

    @pytest.mark.asyncio
    async def test_list_witnesses_returns_profiles(self) -> None:
        """list_witnesses returns WitnessProfile objects from Neo4j."""
        graph_records = [
            {"name": "John Doe", "type": "person", "doc_count": 5, "conn_count": 3, "party_role": "defendant"},
            {"name": "Jane Smith", "type": "person", "doc_count": 2, "conn_count": 1, "party_role": ""},
        ]
        gs = _mock_graph_service(run_query_result=graph_records)
        db = _mock_db()

        witnesses, total = await DepositionService.list_witnesses(db, _MATTER_ID, gs)

        assert total == 2
        assert len(witnesses) == 2
        assert witnesses[0].name == "John Doe"
        assert witnesses[0].document_count == 5
        assert witnesses[0].connection_count == 3
        assert witnesses[0].roles == ["defendant"]
        assert witnesses[1].name == "Jane Smith"
        assert witnesses[1].roles == []

    @pytest.mark.asyncio
    async def test_list_witnesses_empty_graph(self) -> None:
        """list_witnesses returns empty list when no person entities exist."""
        gs = _mock_graph_service(run_query_result=[])
        db = _mock_db()

        witnesses, total = await DepositionService.list_witnesses(db, _MATTER_ID, gs)

        assert total == 0
        assert witnesses == []


# ---------------------------------------------------------------------------
# build_witness_profile
# ---------------------------------------------------------------------------


class TestBuildWitnessProfile:
    """Tests for DepositionService.build_witness_profile."""

    @pytest.mark.asyncio
    async def test_build_witness_profile_found(self) -> None:
        """build_witness_profile returns a full profile for an existing entity."""
        entity = {"name": "John Doe", "type": "person", "mention_count": 5}
        connections = [
            {"target": "Acme Corp", "relationship_type": "EMPLOYED_BY", "target_labels": ["Entity"]},
        ]
        gs = _mock_graph_service(entity=entity, connections=connections)

        doc_rows = [
            {"id": uuid4(), "filename": "doc1.pdf", "summary": "Summary 1", "page_count": 10, "created_at": None},
        ]
        db = _mock_db(doc_rows=doc_rows)

        profile = await DepositionService.build_witness_profile(db, _MATTER_ID, "John Doe", gs)

        assert isinstance(profile, WitnessProfile)
        assert profile.name == "John Doe"
        assert profile.document_count == 1
        assert profile.connection_count == 1
        assert len(profile.connected_entities) == 1
        assert profile.connected_entities[0]["name"] == "Acme Corp"
        assert "employee of Acme Corp" in profile.roles

    @pytest.mark.asyncio
    async def test_build_witness_profile_not_found_raises(self) -> None:
        """build_witness_profile raises 404 when entity is not in graph."""
        gs = _mock_graph_service(entity=None)
        db = _mock_db()

        with pytest.raises(HTTPException) as exc_info:
            await DepositionService.build_witness_profile(db, _MATTER_ID, "Nobody", gs)

        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_build_witness_profile_includes_connections(self) -> None:
        """build_witness_profile includes all entity connections."""
        entity = {"name": "Jane", "type": "person"}
        connections = [
            {"target": "Bob", "relationship_type": "COMMUNICATED_WITH", "target_labels": ["Entity"]},
            {"target": "Corp X", "relationship_type": "MENTIONED_IN", "target_labels": ["Document"]},
        ]
        gs = _mock_graph_service(entity=entity, connections=connections)
        db = _mock_db()

        profile = await DepositionService.build_witness_profile(db, _MATTER_ID, "Jane", gs)

        assert profile.connection_count == 2
        target_names = [c["name"] for c in profile.connected_entities]
        assert "Bob" in target_names
        assert "Corp X" in target_names

    @pytest.mark.asyncio
    async def test_build_witness_profile_includes_document_mentions(self) -> None:
        """build_witness_profile includes document mentions from SQL."""
        entity = {"name": "Alice", "type": "person"}
        gs = _mock_graph_service(entity=entity, connections=[])

        doc_id1, doc_id2 = uuid4(), uuid4()
        doc_rows = [
            {"id": doc_id1, "filename": "contract.pdf", "summary": "A contract", "page_count": 5, "created_at": None},
            {"id": doc_id2, "filename": "email.eml", "summary": "An email", "page_count": 1, "created_at": None},
        ]
        db = _mock_db(doc_rows=doc_rows)

        profile = await DepositionService.build_witness_profile(db, _MATTER_ID, "Alice", gs)

        assert profile.document_count == 2
        assert len(profile.document_mentions) == 2
        filenames = [m["filename"] for m in profile.document_mentions]
        assert "contract.pdf" in filenames
        assert "email.eml" in filenames


# ---------------------------------------------------------------------------
# generate_prep_package
# ---------------------------------------------------------------------------


class TestGeneratePrepPackage:
    """Tests for DepositionService.generate_prep_package."""

    @pytest.mark.asyncio
    async def test_generate_prep_package_success(self) -> None:
        """generate_prep_package returns a complete DepositionPrepResponse."""
        entity = {"name": "John Doe", "type": "person"}
        connections = [{"target": "Acme", "relationship_type": "WORKS_FOR", "target_labels": ["Entity"]}]
        gs = _mock_graph_service(entity=entity, connections=connections)

        doc_id = uuid4()
        doc_rows = [
            {"id": doc_id, "filename": "doc.pdf", "summary": "Key document", "page_count": 3, "created_at": None},
        ]
        db = _mock_db(doc_rows=doc_rows)

        questions_json = json.dumps(
            [
                {
                    "question": "What is your role at Acme?",
                    "category": "relationship",
                    "basis_document_ids": [str(doc_id)],
                    "rationale": "Clarify employment relationship.",
                },
                {
                    "question": "When did you first see the document?",
                    "category": "timeline",
                    "basis_document_ids": [str(doc_id)],
                    "rationale": "Establish timeline.",
                },
            ]
        )

        mock_llm = AsyncMock()
        mock_llm.complete = AsyncMock(return_value=questions_json)

        result = await DepositionService.generate_prep_package(
            db=db,
            matter_id=_MATTER_ID,
            witness_name="John Doe",
            graph_service=gs,
            llm=mock_llm,
            max_questions=15,
        )

        assert result.witness.name == "John Doe"
        assert len(result.questions) == 2
        assert result.questions[0].category == QuestionCategory.relationship
        assert result.questions[1].category == QuestionCategory.timeline
        mock_llm.complete.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_prep_package_with_focus_categories(self) -> None:
        """generate_prep_package passes focus categories to the LLM prompt."""
        entity = {"name": "Jane", "type": "person"}
        gs = _mock_graph_service(entity=entity, connections=[])
        db = _mock_db()

        mock_llm = AsyncMock()
        mock_llm.complete = AsyncMock(return_value="[]")

        result = await DepositionService.generate_prep_package(
            db=db,
            matter_id=_MATTER_ID,
            witness_name="Jane",
            graph_service=gs,
            llm=mock_llm,
            focus_categories=[QuestionCategory.timeline, QuestionCategory.inconsistency],
        )

        # Verify the prompt included focus categories
        call_args = mock_llm.complete.call_args
        prompt_content = (
            call_args[1]["messages"][0]["content"] if "messages" in call_args[1] else call_args[0][0][0]["content"]
        )
        assert "timeline" in prompt_content
        assert "inconsistency" in prompt_content
        assert result.questions == []

    @pytest.mark.asyncio
    async def test_generate_prep_package_witness_not_found(self) -> None:
        """generate_prep_package raises 404 when witness does not exist."""
        gs = _mock_graph_service(entity=None)
        db = _mock_db()
        mock_llm = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await DepositionService.generate_prep_package(
                db=db,
                matter_id=_MATTER_ID,
                witness_name="Ghost",
                graph_service=gs,
                llm=mock_llm,
            )

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_generate_prep_package_max_questions(self) -> None:
        """generate_prep_package respects max_questions limit."""
        entity = {"name": "Bob", "type": "person"}
        gs = _mock_graph_service(entity=entity, connections=[])
        db = _mock_db()

        # LLM returns more questions than max
        many_questions = json.dumps(
            [
                {
                    "question": f"Question {i}?",
                    "category": "timeline",
                    "basis_document_ids": [],
                    "rationale": f"Reason {i}",
                }
                for i in range(20)
            ]
        )
        mock_llm = AsyncMock()
        mock_llm.complete = AsyncMock(return_value=many_questions)

        result = await DepositionService.generate_prep_package(
            db=db,
            matter_id=_MATTER_ID,
            witness_name="Bob",
            graph_service=gs,
            llm=mock_llm,
            max_questions=5,
        )

        assert len(result.questions) <= 5


# ---------------------------------------------------------------------------
# _parse_questions
# ---------------------------------------------------------------------------


class TestParseQuestions:
    """Tests for the _parse_questions helper."""

    def test_parse_valid_json(self) -> None:
        """_parse_questions correctly parses valid JSON array."""
        raw = json.dumps(
            [
                {"question": "Q1?", "category": "relationship", "basis_document_ids": ["doc-1"], "rationale": "R1"},
            ]
        )
        result = _parse_questions(raw, 10)
        assert len(result) == 1
        assert result[0].question == "Q1?"
        assert result[0].category == QuestionCategory.relationship

    def test_parse_invalid_json(self) -> None:
        """_parse_questions returns empty list for invalid JSON."""
        result = _parse_questions("not json at all", 10)
        assert result == []

    def test_parse_invalid_category_defaults(self) -> None:
        """_parse_questions defaults invalid categories to document_specific."""
        raw = json.dumps(
            [
                {"question": "Q1?", "category": "bogus_category", "rationale": "R1"},
            ]
        )
        result = _parse_questions(raw, 10)
        assert len(result) == 1
        assert result[0].category == QuestionCategory.document_specific
