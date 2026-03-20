"""Tests for the pre-embedded FBI dataset import script.

Tests cover:
  - Schema detection (rich FBI vs sparse House Oversight)
  - Parquet reading and document grouping
  - DocumentGroup properties (full_text, page_count, content_hash, metadata)
  - ChunkRecord data class
  - NER extraction helper (with mocked extractor)
  - Resume/dedup logic
  - Qdrant batch upsert (mocked)
  - CLI argument validation
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_fbi_parquet(path: Path, n_docs: int = 3, chunks_per_doc: int = 2) -> Path:
    """Create a Parquet file mimicking the FBI dataset schema."""
    rows = []
    for doc_i in range(n_docs):
        source_file = f"FBI_VOL01_{doc_i:04d}.pdf"
        for chunk_j in range(chunks_per_doc):
            rows.append(
                {
                    "source_file": source_file,
                    "chunk_index": chunk_j,
                    "text": f"Document {doc_i} chunk {chunk_j}. FBI interview summary regarding subject activities in Palm Beach County.",
                    "embedding": np.random.rand(768).tolist(),
                    "page_number": chunk_j + 1,
                    "bates_number": f"FBI-{doc_i:04d}-{chunk_j:03d}",
                    "ocr_confidence": 0.95,
                    "volume": "Volume 01",
                    "doc_type": "interview",
                }
            )
    df = pd.DataFrame(rows)
    pq_path = path / "fbi_test.parquet"
    df.to_parquet(pq_path, index=False)
    return pq_path


def _make_fbi_jsonl_parquet(path: Path, n_docs: int = 3, chunks_per_doc: int = 2) -> Path:
    """Create a Parquet file mimicking the FBI JSONL schema (chunk_text, source_path, etc.)."""
    rows = []
    for doc_i in range(n_docs):
        source_path = f"VOL{doc_i + 1:05d}/FBI_EFTA_{doc_i:04d}.pdf"
        for chunk_j in range(chunks_per_doc):
            rows.append(
                {
                    "id": f"uuid-{doc_i}-{chunk_j}",
                    "bates_number": f"EFTA{doc_i * 10 + chunk_j:08d}",
                    "bates_range": f"EFTA{doc_i * 10 + chunk_j:08d}-EFTA{doc_i * 10 + chunk_j:08d}",
                    "source_volume": doc_i + 1,
                    "source_path": source_path,
                    "doc_type": "typed_memo",
                    "ocr_confidence": 0.9,
                    "ocr_engine": "textract",
                    "page_number": chunk_j + 1,
                    "total_pages": chunks_per_doc,
                    "chunk_index": chunk_j,
                    "total_chunks": chunks_per_doc,
                    "chunk_text": f"FBI JSONL Document {doc_i} chunk {chunk_j}.",
                    "embedding": np.random.rand(768).tolist(),
                    "ingested_at": 1703123456,
                }
            )
    df = pd.DataFrame(rows)
    pq_path = path / "fbi_jsonl_test.parquet"
    df.to_parquet(pq_path, index=False)
    return pq_path


def _make_sparse_parquet(path: Path, n_chunks: int = 5) -> Path:
    """Create a Parquet file mimicking the House Oversight schema (sparse)."""
    rows = []
    for i in range(n_chunks):
        rows.append(
            {
                "source_file": f"IMAGES-{i}-HOUSE_OVERSIGHT_{i:06d}.txt",
                "chunk_index": i,
                "text": f"Chunk {i}. Deposition text from the House Oversight release with enough content to be meaningful.",
                "embedding": np.random.rand(768).tolist(),
            }
        )
    df = pd.DataFrame(rows)
    pq_path = path / "house_oversight_test.parquet"
    df.to_parquet(pq_path, index=False)
    return pq_path


# ---------------------------------------------------------------------------
# 1. Schema detection
# ---------------------------------------------------------------------------


class TestSchemaDetection:
    def test_detects_rich_fbi_schema(self) -> None:
        from scripts.import_fbi_dataset import detect_schema

        cols = [
            "source_file",
            "chunk_index",
            "text",
            "embedding",
            "page_number",
            "bates_number",
            "ocr_confidence",
            "volume",
            "doc_type",
        ]
        mapping = detect_schema(cols)

        assert mapping["text"] == "text"
        assert mapping["embedding"] == "embedding"
        assert mapping["source_file"] == "source_file"
        assert mapping["page_number"] == "page_number"
        assert mapping["bates_number"] == "bates_number"
        assert mapping["ocr_confidence"] == "ocr_confidence"
        assert mapping["volume"] == "volume"
        assert mapping["doc_type"] == "doc_type"

    def test_detects_sparse_schema(self) -> None:
        from scripts.import_fbi_dataset import detect_schema

        cols = ["source_file", "chunk_index", "text", "embedding"]
        mapping = detect_schema(cols)

        assert mapping["text"] == "text"
        assert mapping["embedding"] == "embedding"
        assert mapping["source_file"] == "source_file"
        assert mapping["page_number"] is None
        assert mapping["bates_number"] is None

    def test_missing_text_column_raises(self) -> None:
        from scripts.import_fbi_dataset import detect_schema

        with pytest.raises(ValueError, match="text"):
            detect_schema(["embedding", "source_file"])

    def test_missing_embedding_column_raises(self) -> None:
        from scripts.import_fbi_dataset import detect_schema

        with pytest.raises(ValueError, match="embedding"):
            detect_schema(["text", "source_file"])

    def test_filename_column_alias(self) -> None:
        from scripts.import_fbi_dataset import detect_schema

        cols = ["filename", "text", "embedding"]
        mapping = detect_schema(cols)
        assert mapping["source_file"] == "filename"

    def test_fbi_jsonl_schema(self) -> None:
        """FBI JSONL uses chunk_text, source_path, source_volume."""
        from scripts.import_fbi_dataset import detect_schema

        cols = [
            "id",
            "bates_number",
            "bates_range",
            "source_volume",
            "source_path",
            "doc_type",
            "ocr_confidence",
            "ocr_engine",
            "page_number",
            "total_pages",
            "chunk_index",
            "total_chunks",
            "chunk_text",
            "embedding",
            "ingested_at",
        ]
        mapping = detect_schema(cols)

        assert mapping["text"] == "chunk_text"
        assert mapping["embedding"] == "embedding"
        assert mapping["source_file"] == "source_path"
        assert mapping["chunk_index"] == "chunk_index"
        assert mapping["page_number"] == "page_number"
        assert mapping["bates_number"] == "bates_number"
        assert mapping["ocr_confidence"] == "ocr_confidence"
        assert mapping["volume"] == "source_volume"
        assert mapping["doc_type"] == "doc_type"

    def test_chunk_text_alias_accepted(self) -> None:
        """chunk_text should be accepted as a text column alias."""
        from scripts.import_fbi_dataset import detect_schema

        cols = ["chunk_text", "embedding"]
        mapping = detect_schema(cols)
        assert mapping["text"] == "chunk_text"

    def test_source_path_alias(self) -> None:
        from scripts.import_fbi_dataset import detect_schema

        cols = ["source_path", "text", "embedding"]
        mapping = detect_schema(cols)
        assert mapping["source_file"] == "source_path"

    def test_bates_range_alias(self) -> None:
        from scripts.import_fbi_dataset import detect_schema

        cols = ["bates_range", "text", "embedding"]
        mapping = detect_schema(cols)
        assert mapping["bates_number"] == "bates_range"


# ---------------------------------------------------------------------------
# 2. Document grouping
# ---------------------------------------------------------------------------


class TestReadAndGroup:
    def test_groups_by_source_file(self, tmp_path: Path) -> None:
        from scripts.import_fbi_dataset import detect_schema, read_and_group

        pq = _make_fbi_parquet(tmp_path, n_docs=3, chunks_per_doc=2)
        df = pd.read_parquet(pq)
        schema = detect_schema(list(df.columns))
        groups = read_and_group(pq, schema)

        assert len(groups) == 3
        for g in groups:
            assert len(g.chunks) == 2

    def test_respects_limit(self, tmp_path: Path) -> None:
        from scripts.import_fbi_dataset import detect_schema, read_and_group

        pq = _make_fbi_parquet(tmp_path, n_docs=10, chunks_per_doc=2)
        df = pd.read_parquet(pq)
        schema = detect_schema(list(df.columns))
        groups = read_and_group(pq, schema, limit=3)

        assert len(groups) == 3

    def test_skips_empty_text(self, tmp_path: Path) -> None:
        from scripts.import_fbi_dataset import detect_schema, read_and_group

        rows = [
            {"source_file": "doc1.pdf", "chunk_index": 0, "text": "", "embedding": np.random.rand(768).tolist()},
            {"source_file": "doc2.pdf", "chunk_index": 0, "text": "   ", "embedding": np.random.rand(768).tolist()},
            {
                "source_file": "doc3.pdf",
                "chunk_index": 0,
                "text": "Valid text for import.",
                "embedding": np.random.rand(768).tolist(),
            },
        ]
        df = pd.DataFrame(rows)
        pq = tmp_path / "test.parquet"
        df.to_parquet(pq)
        schema = detect_schema(list(df.columns))
        groups = read_and_group(pq, schema)

        assert len(groups) == 1
        assert groups[0].source_file == "doc3.pdf"

    def test_sparse_schema_grouped(self, tmp_path: Path) -> None:
        from scripts.import_fbi_dataset import detect_schema, read_and_group

        pq = _make_sparse_parquet(tmp_path, n_chunks=5)
        df = pd.read_parquet(pq)
        schema = detect_schema(list(df.columns))
        groups = read_and_group(pq, schema)

        # Each chunk has a unique source_file
        assert len(groups) == 5

    def test_fbi_jsonl_schema_groups(self, tmp_path: Path) -> None:
        """FBI JSONL format (chunk_text, source_path) groups correctly."""
        from scripts.import_fbi_dataset import detect_schema, read_and_group

        pq = _make_fbi_jsonl_parquet(tmp_path, n_docs=3, chunks_per_doc=2)
        df = pd.read_parquet(pq)
        schema = detect_schema(list(df.columns))
        groups = read_and_group(pq, schema)

        assert len(groups) == 3
        for g in groups:
            assert len(g.chunks) == 2
            assert g.chunks[0].text.startswith("FBI JSONL")
            assert g.source_file.startswith("VOL")


# ---------------------------------------------------------------------------
# 3. DocumentGroup properties
# ---------------------------------------------------------------------------


class TestDocumentGroup:
    def test_full_text_ordered_by_chunk_index(self) -> None:
        from scripts.import_fbi_dataset import ChunkRecord, DocumentGroup

        group = DocumentGroup(
            source_file="test.pdf",
            chunks=[
                ChunkRecord(text="Second chunk.", embedding=[], chunk_index=1, source_file="test.pdf"),
                ChunkRecord(text="First chunk.", embedding=[], chunk_index=0, source_file="test.pdf"),
                ChunkRecord(text="Third chunk.", embedding=[], chunk_index=2, source_file="test.pdf"),
            ],
        )

        assert group.full_text == "First chunk.\n\nSecond chunk.\n\nThird chunk."

    def test_page_count_from_chunks(self) -> None:
        from scripts.import_fbi_dataset import ChunkRecord, DocumentGroup

        group = DocumentGroup(
            source_file="test.pdf",
            chunks=[
                ChunkRecord(text="a", embedding=[], chunk_index=0, source_file="test.pdf", page_number=1),
                ChunkRecord(text="b", embedding=[], chunk_index=1, source_file="test.pdf", page_number=5),
                ChunkRecord(text="c", embedding=[], chunk_index=2, source_file="test.pdf", page_number=3),
            ],
        )

        assert group.page_count == 5

    def test_page_count_defaults_to_1(self) -> None:
        from scripts.import_fbi_dataset import ChunkRecord, DocumentGroup

        group = DocumentGroup(
            source_file="test.pdf",
            chunks=[
                ChunkRecord(text="a", embedding=[], chunk_index=0, source_file="test.pdf"),
            ],
        )

        assert group.page_count == 1

    def test_content_hash_deterministic(self) -> None:
        from scripts.import_fbi_dataset import ChunkRecord, DocumentGroup

        chunks = [ChunkRecord(text="Hello world", embedding=[], chunk_index=0, source_file="test.pdf")]
        g1 = DocumentGroup(source_file="test.pdf", chunks=list(chunks))
        g2 = DocumentGroup(source_file="test.pdf", chunks=list(chunks))

        assert g1.content_hash == g2.content_hash
        assert len(g1.content_hash) == 16

    def test_metadata_includes_bates(self) -> None:
        from scripts.import_fbi_dataset import ChunkRecord, DocumentGroup

        group = DocumentGroup(
            source_file="FBI_VOL01.pdf",
            chunks=[
                ChunkRecord(
                    text="text",
                    embedding=[],
                    chunk_index=0,
                    source_file="FBI_VOL01.pdf",
                    bates_number="FBI-0001",
                    volume="Vol 01",
                    ocr_confidence=0.95,
                    doc_type_hint="interview",
                ),
                ChunkRecord(
                    text="text2",
                    embedding=[],
                    chunk_index=1,
                    source_file="FBI_VOL01.pdf",
                    ocr_confidence=0.85,
                ),
            ],
        )

        meta = group.metadata
        assert meta["bates_number"] == "FBI-0001"
        assert meta["volume"] == "Vol 01"
        assert meta["ocr_confidence"] == 0.9  # average of 0.95 and 0.85
        assert meta["doc_type"] == "interview"


# ---------------------------------------------------------------------------
# 4. NER extraction helper
# ---------------------------------------------------------------------------


class TestExtractEntities:
    def test_extracts_and_deduplicates(self) -> None:
        from scripts.import_fbi_dataset import ChunkRecord, extract_entities

        mock_extractor = MagicMock()
        entity1 = MagicMock(text="Jeffrey Epstein", type="person")
        entity2 = MagicMock(text="Palm Beach", type="location")
        entity3 = MagicMock(text="Jeffrey Epstein", type="person")  # duplicate

        mock_extractor.extract.side_effect = [
            [entity1, entity2],
            [entity3],
        ]

        chunks = [
            ChunkRecord(text="chunk1", embedding=[], chunk_index=0, source_file="test.pdf", page_number=1),
            ChunkRecord(text="chunk2", embedding=[], chunk_index=1, source_file="test.pdf", page_number=2),
        ]

        entities = extract_entities(chunks, mock_extractor)

        assert len(entities) == 2  # deduped
        assert entities[0]["name"] == "Jeffrey Epstein"
        assert entities[0]["type"] == "person"
        assert entities[0]["page_number"] == 1
        assert entities[1]["name"] == "Palm Beach"

    def test_handles_empty_extraction(self) -> None:
        from scripts.import_fbi_dataset import ChunkRecord, extract_entities

        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = []

        chunks = [ChunkRecord(text="chunk", embedding=[], chunk_index=0, source_file="test.pdf")]
        entities = extract_entities(chunks, mock_extractor)

        assert entities == []


# ---------------------------------------------------------------------------
# 5. Qdrant upsert
# ---------------------------------------------------------------------------


class TestQdrantUpsert:
    @patch("qdrant_client.QdrantClient")
    def test_upserts_in_batches(self, mock_qdrant_cls) -> None:
        from scripts.import_fbi_dataset import ChunkRecord, DocumentGroup, upsert_chunks_to_qdrant

        mock_client = MagicMock()
        mock_qdrant_cls.return_value = mock_client

        # Create a doc with 150 chunks (should produce 2 batches: 100 + 50)
        chunks = [
            ChunkRecord(
                text=f"chunk {i}",
                embedding=[0.1] * 768,
                chunk_index=i,
                source_file="test.pdf",
                page_number=i + 1,
            )
            for i in range(150)
        ]
        doc_group = DocumentGroup(source_file="test.pdf", chunks=chunks)

        settings = MagicMock()
        settings.qdrant_url = "http://localhost:6333"

        chunk_data = upsert_chunks_to_qdrant(
            settings,
            "doc-id-123",
            doc_group,
            "matter-id-456",
            citation_quality="full",
            use_named_vectors=True,
        )

        # 2 batch calls
        assert mock_client.upsert.call_count == 2
        assert len(chunk_data) == 150

        # Verify first batch has 100 points
        first_call = mock_client.upsert.call_args_list[0]
        assert len(first_call.kwargs["points"]) == 100

    @patch("qdrant_client.QdrantClient")
    def test_payload_includes_metadata(self, mock_qdrant_cls) -> None:
        from scripts.import_fbi_dataset import ChunkRecord, DocumentGroup, upsert_chunks_to_qdrant

        mock_client = MagicMock()
        mock_qdrant_cls.return_value = mock_client

        chunks = [
            ChunkRecord(
                text="test chunk text",
                embedding=[0.1] * 768,
                chunk_index=0,
                source_file="FBI_0001.pdf",
                page_number=5,
                bates_number="FBI-0001-000",
                ocr_confidence=0.92,
            ),
        ]
        doc_group = DocumentGroup(source_file="FBI_0001.pdf", chunks=chunks)

        settings = MagicMock()
        settings.qdrant_url = "http://localhost:6333"

        upsert_chunks_to_qdrant(
            settings,
            "doc-123",
            doc_group,
            "matter-456",
            citation_quality="full",
            use_named_vectors=True,
        )

        call_args = mock_client.upsert.call_args
        point = call_args.kwargs["points"][0]

        assert point.payload["page_number"] == 5
        assert point.payload["bates_number"] == "FBI-0001-000"
        assert point.payload["ocr_confidence"] == 0.92
        assert point.payload["matter_id"] == "matter-456"
        assert point.payload["doc_id"] == "doc-123"
        assert point.payload["citation_quality"] == "full"
        assert point.payload["chunk_text"] == "test chunk text"

    @patch("qdrant_client.QdrantClient")
    def test_named_vs_unnamed_vectors(self, mock_qdrant_cls) -> None:
        from scripts.import_fbi_dataset import ChunkRecord, DocumentGroup, upsert_chunks_to_qdrant

        mock_client = MagicMock()
        mock_qdrant_cls.return_value = mock_client

        chunks = [ChunkRecord(text="test", embedding=[0.1] * 768, chunk_index=0, source_file="test.pdf")]
        doc_group = DocumentGroup(source_file="test.pdf", chunks=chunks)
        settings = MagicMock()
        settings.qdrant_url = "http://localhost:6333"

        # Named vectors
        upsert_chunks_to_qdrant(settings, "d", doc_group, "m", use_named_vectors=True)
        point_named = mock_client.upsert.call_args.kwargs["points"][0]
        assert isinstance(point_named.vector, dict)
        assert "dense" in point_named.vector

        mock_client.reset_mock()

        # Unnamed vectors
        upsert_chunks_to_qdrant(settings, "d", doc_group, "m", use_named_vectors=False)
        point_unnamed = mock_client.upsert.call_args.kwargs["points"][0]
        assert isinstance(point_unnamed.vector, list)


# ---------------------------------------------------------------------------
# 5b. total_pages support
# ---------------------------------------------------------------------------


class TestTotalPages:
    def test_total_pages_detected_in_schema(self) -> None:
        """detect_schema maps total_pages when present."""
        from scripts.import_fbi_dataset import detect_schema

        cols = ["text", "embedding", "source_file", "total_pages"]
        mapping = detect_schema(cols)
        assert mapping["total_pages"] == "total_pages"

    def test_total_pages_absent_maps_to_none(self) -> None:
        from scripts.import_fbi_dataset import detect_schema

        cols = ["text", "embedding", "source_file"]
        mapping = detect_schema(cols)
        assert mapping["total_pages"] is None

    def test_total_pages_preferred_over_max_page_number(self) -> None:
        """When total_pages is set, page_count should use it instead of max(page_number)."""
        from scripts.import_fbi_dataset import ChunkRecord, DocumentGroup

        group = DocumentGroup(
            source_file="test.pdf",
            chunks=[
                ChunkRecord(
                    text="a",
                    embedding=[],
                    chunk_index=0,
                    source_file="test.pdf",
                    page_number=1,
                    total_pages=42,
                ),
                ChunkRecord(
                    text="b",
                    embedding=[],
                    chunk_index=1,
                    source_file="test.pdf",
                    page_number=5,
                    total_pages=42,
                ),
            ],
        )
        # total_pages=42 should win over max(page_number)=5
        assert group.page_count == 42

    def test_total_pages_falls_back_when_absent(self) -> None:
        """When total_pages is None, falls back to max(page_number)."""
        from scripts.import_fbi_dataset import ChunkRecord, DocumentGroup

        group = DocumentGroup(
            source_file="test.pdf",
            chunks=[
                ChunkRecord(text="a", embedding=[], chunk_index=0, source_file="test.pdf", page_number=1),
                ChunkRecord(text="b", embedding=[], chunk_index=1, source_file="test.pdf", page_number=5),
            ],
        )
        assert group.page_count == 5

    def test_total_pages_read_from_parquet(self, tmp_path: Path) -> None:
        """total_pages is extracted from the Parquet file via read_and_group."""
        from scripts.import_fbi_dataset import detect_schema, read_and_group

        pq = _make_fbi_jsonl_parquet(tmp_path, n_docs=2, chunks_per_doc=3)
        df = pd.read_parquet(pq)
        schema = detect_schema(list(df.columns))
        groups = read_and_group(pq, schema)

        # The JSONL fixture sets total_pages = chunks_per_doc = 3
        for g in groups:
            assert g.page_count == 3
            assert g.chunks[0].total_pages == 3


class TestConcurrency:
    def test_process_one_document_callable(self) -> None:
        """_process_one_document exists and is callable."""
        from scripts.import_fbi_dataset import _process_one_document

        assert callable(_process_one_document)

    @patch("scripts.import_fbi_dataset.upsert_chunks_to_qdrant")
    @patch("scripts.import_fbi_dataset.upload_to_minio")
    @patch("scripts.import_fbi_dataset.create_job_and_document")
    def test_process_one_document_returns_counts(
        self,
        mock_create,
        mock_minio,
        mock_qdrant,
    ) -> None:
        """_process_one_document returns (chunk_count, entity_count) tuple."""
        from scripts.import_fbi_dataset import ChunkRecord, DocumentGroup, _process_one_document

        mock_create.return_value = ("job-1", "doc-1")
        mock_qdrant.return_value = [{"chunk_id": "c1", "text_preview": "t", "page_number": 1, "qdrant_point_id": "c1"}]

        doc_group = DocumentGroup(
            source_file="test.pdf",
            chunks=[ChunkRecord(text="test", embedding=[0.1] * 768, chunk_index=0, source_file="test.pdf")],
        )

        chunks, ents = _process_one_document(
            doc_group,
            engine=MagicMock(),
            settings=MagicMock(),
            matter_id="m-1",
            dataset_id=None,
            import_source="test",
            citation_quality="full",
            use_named_vectors=True,
            extractor=None,
            skip_minio=True,
            skip_neo4j=True,
        )

        assert chunks == 1
        assert ents == 0
        mock_create.assert_called_once()
        mock_qdrant.assert_called_once()


# ---------------------------------------------------------------------------
# 6. Resume logic
# ---------------------------------------------------------------------------


class TestResume:
    @patch("scripts.import_fbi_dataset._get_engine")
    def test_check_resume_found(self, mock_engine_fn) -> None:
        from scripts.import_fbi_dataset import check_resume

        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.execute.return_value.first.return_value = MagicMock(id="existing-id")

        assert check_resume(mock_engine, "hash123", "matter-456") is True

    @patch("scripts.import_fbi_dataset._get_engine")
    def test_check_resume_not_found(self, mock_engine_fn) -> None:
        from scripts.import_fbi_dataset import check_resume

        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.execute.return_value.first.return_value = None

        assert check_resume(mock_engine, "hash123", "matter-456") is False


# ---------------------------------------------------------------------------
# 7. Citation quality in payload
# ---------------------------------------------------------------------------


class TestCitationQuality:
    @patch("qdrant_client.QdrantClient")
    def test_degraded_citation_quality(self, mock_qdrant_cls) -> None:
        from scripts.import_fbi_dataset import ChunkRecord, DocumentGroup, upsert_chunks_to_qdrant

        mock_client = MagicMock()
        mock_qdrant_cls.return_value = mock_client

        chunks = [ChunkRecord(text="test", embedding=[0.1] * 768, chunk_index=0, source_file="test.pdf")]
        doc_group = DocumentGroup(source_file="test.pdf", chunks=chunks)
        settings = MagicMock()
        settings.qdrant_url = "http://localhost:6333"

        upsert_chunks_to_qdrant(settings, "d", doc_group, "m", citation_quality="degraded")

        point = mock_client.upsert.call_args.kwargs["points"][0]
        assert point.payload["citation_quality"] == "degraded"


# ---------------------------------------------------------------------------
# 8. Chunk data for Neo4j
# ---------------------------------------------------------------------------


class TestChunkDataForNeo4j:
    @patch("qdrant_client.QdrantClient")
    def test_returns_chunk_data_list(self, mock_qdrant_cls) -> None:
        from scripts.import_fbi_dataset import ChunkRecord, DocumentGroup, upsert_chunks_to_qdrant

        mock_client = MagicMock()
        mock_qdrant_cls.return_value = mock_client

        chunks = [
            ChunkRecord(
                text="chunk 0 text", embedding=[0.1] * 768, chunk_index=0, source_file="test.pdf", page_number=1
            ),
            ChunkRecord(
                text="chunk 1 text", embedding=[0.2] * 768, chunk_index=1, source_file="test.pdf", page_number=2
            ),
        ]
        doc_group = DocumentGroup(source_file="test.pdf", chunks=chunks)
        settings = MagicMock()
        settings.qdrant_url = "http://localhost:6333"

        chunk_data = upsert_chunks_to_qdrant(settings, "doc-123", doc_group, "matter-456")

        assert len(chunk_data) == 2
        assert chunk_data[0]["text_preview"].startswith("chunk 0")
        assert chunk_data[0]["page_number"] == 1
        assert chunk_data[1]["page_number"] == 2
        assert "chunk_id" in chunk_data[0]
        assert "qdrant_point_id" in chunk_data[0]
