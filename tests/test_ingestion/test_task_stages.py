"""Tests for the decomposed pipeline stage functions and ZIP helpers.

Validates that each stage function correctly populates the _PipelineContext
and that the ZIP skip/process helpers work as expected.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import MagicMock, patch

from app.ingestion.tasks import (
    _PipelineContext,
    _process_zip_member,
    _should_skip_zip_member,
    _stage_chunk,
    _stage_complete,
    _stage_embed,
    _stage_extract,
    _stage_index,
    _stage_parse,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_settings() -> MagicMock:
    """Create a mock Settings object with safe defaults for tests."""
    s = MagicMock()
    s.minio_use_ssl = False
    s.minio_endpoint = "localhost:9000"
    s.minio_access_key = "test"
    s.minio_secret_key = "test"
    s.minio_bucket = "test"
    s.postgres_url_sync = "postgresql://test:test@localhost/test"
    s.qdrant_url = "http://localhost:6333"
    s.neo4j_uri = "bolt://localhost:7687"
    s.neo4j_user = "neo4j"
    s.neo4j_password = "test"
    s.chunk_size = 512
    s.chunk_overlap = 64
    s.enable_visual_embeddings = False
    s.enable_sparse_embeddings = False
    s.enable_relationship_extraction = False
    s.enable_email_threading = False
    s.enable_near_duplicate_detection = False
    s.enable_hot_doc_detection = False
    s.gliner_model = "test-model"
    s.embedding_provider = "openai"
    s.openai_api_key = "test-key"
    s.embedding_model = "text-embedding-3-large"
    s.embedding_dimensions = 1024
    s.embedding_batch_size = 100
    return s


def _make_ctx(**overrides) -> _PipelineContext:
    """Create a _PipelineContext with sensible defaults."""
    defaults = {
        "settings": _make_mock_settings(),
        "engine": MagicMock(),
        "job_id": "job-001",
        "minio_path": "raw/job-001/test.pdf",
        "filename": "test.pdf",
        "matter_id": "matter-001",
    }
    defaults.update(overrides)
    return _PipelineContext(**defaults)


@dataclass
class _FakePage:
    page_number: int
    text: str = "Page text"
    tables: list[str] = field(default_factory=list)
    images: list[bytes] = field(default_factory=list)


@dataclass
class _FakeParseResult:
    text: str = "Parsed document text for testing."
    pages: list[_FakePage] = field(default_factory=lambda: [_FakePage(page_number=1)])
    metadata: dict = field(default_factory=dict)
    page_count: int = 1


@dataclass
class _FakeChunk:
    chunk_index: int
    text: str
    token_count: int
    metadata: dict = field(default_factory=dict)
    context_prefix: str | None = None


@dataclass
class _FakeEntity:
    text: str
    type: str


# ---------------------------------------------------------------------------
# Stage tests
# ---------------------------------------------------------------------------


class TestStageParse:
    """Tests for _stage_parse."""

    def test_populates_context_fields(self):
        """_stage_parse should populate parse_result, content_hash, file_size."""
        ctx = _make_ctx()
        fake_parse = _FakeParseResult()

        with (
            patch("app.ingestion.tasks._update_stage"),
            patch("app.ingestion.tasks._download_from_minio", return_value=b"fake pdf bytes"),
            patch("app.ingestion.tasks._upload_to_minio"),
            patch("app.ingestion.parser.DocumentParser") as mock_parser,
        ):
            mock_parser.return_value.parse.return_value = fake_parse
            _stage_parse(ctx)

        assert ctx.parse_result is fake_parse
        assert ctx.file_size == len(b"fake pdf bytes")
        assert ctx.content_hash != ""
        assert ctx.progress.get("pages_parsed") == 1


class TestStageChunk:
    """Tests for _stage_chunk."""

    def test_populates_chunks_and_doc_type(self):
        """_stage_chunk should populate chunks, doc_type, document_type."""
        ctx = _make_ctx()
        ctx.parse_result = _FakeParseResult()

        fake_chunks = [_FakeChunk(chunk_index=0, text="chunk 1", token_count=10)]

        with (
            patch("app.ingestion.tasks._update_stage"),
            patch("app.ingestion.chunker.TextChunker.chunk", return_value=fake_chunks),
        ):
            _stage_chunk(ctx)

        assert ctx.chunks == fake_chunks
        assert ctx.doc_type == "document"  # .pdf -> document
        assert ctx.document_type == "document"
        assert ctx.progress.get("chunks_created") == 1


class TestStageEmbed:
    """Tests for _stage_embed."""

    def test_populates_embeddings(self):
        """_stage_embed should populate embeddings list."""
        ctx = _make_ctx()
        ctx.chunks = [_FakeChunk(chunk_index=0, text="test chunk", token_count=5)]

        fake_embeddings = [[0.1, 0.2, 0.3]]

        with (
            patch("app.ingestion.tasks._update_stage"),
            patch("app.ingestion.tasks._embed_chunks", return_value=fake_embeddings),
            patch("app.ingestion.tasks.asyncio.run", side_effect=lambda coro: fake_embeddings),
        ):
            _stage_embed(ctx)

        assert ctx.embeddings == fake_embeddings
        assert ctx.sparse_embeddings == []
        assert ctx.visual_page_embeddings == []
        assert ctx.progress.get("embeddings_generated") == 1


class TestStageExtract:
    """Tests for _stage_extract."""

    def test_populates_entities(self):
        """_stage_extract should populate all_entities with deduplicated entities."""
        ctx = _make_ctx()
        ctx.chunks = [
            _FakeChunk(chunk_index=0, text="John Smith works at Acme.", token_count=10),
        ]

        fake_entities = [
            _FakeEntity(text="John Smith", type="PERSON"),
            _FakeEntity(text="Acme", type="ORGANIZATION"),
        ]

        with (
            patch("app.ingestion.tasks._update_stage"),
            patch("app.entities.extractor.EntityExtractor.extract", return_value=fake_entities),
        ):
            _stage_extract(ctx)

        assert len(ctx.all_entities) == 2
        assert ctx.all_entities[0]["name"] == "John Smith"
        assert ctx.all_entities[1]["name"] == "Acme"
        assert ctx.progress.get("entities_extracted") == 2

    def test_normalizes_entity_name_whitespace(self):
        """Entity names with embedded newlines/tabs should be collapsed to single spaces."""
        ctx = _make_ctx()
        ctx.chunks = [
            _FakeChunk(chunk_index=0, text="Michael Torres works here.", token_count=10),
        ]

        fake_entities = [
            _FakeEntity(text="Michael\nTorres", type="PERSON"),
            _FakeEntity(text="  Jane\t\tDoe  ", type="PERSON"),
        ]

        with (
            patch("app.ingestion.tasks._update_stage"),
            patch("app.entities.extractor.EntityExtractor.extract", return_value=fake_entities),
        ):
            _stage_extract(ctx)

        assert len(ctx.all_entities) == 2
        assert ctx.all_entities[0]["name"] == "Michael Torres"
        assert ctx.all_entities[1]["name"] == "Jane Doe"

    def test_deduplicates_after_whitespace_normalization(self):
        """Entities that differ only in whitespace should be deduplicated."""
        ctx = _make_ctx()
        ctx.chunks = [
            _FakeChunk(chunk_index=0, text="Test text.", token_count=10),
        ]

        fake_entities = [
            _FakeEntity(text="Michael Torres", type="PERSON"),
            _FakeEntity(text="Michael\nTorres", type="PERSON"),
        ]

        with (
            patch("app.ingestion.tasks._update_stage"),
            patch("app.entities.extractor.EntityExtractor.extract", return_value=fake_entities),
        ):
            _stage_extract(ctx)

        assert len(ctx.all_entities) == 1
        assert ctx.all_entities[0]["name"] == "Michael Torres"


class TestStageIndex:
    """Tests for _stage_index."""

    def test_creates_qdrant_points_and_neo4j_data(self):
        """_stage_index should upsert to Qdrant and call Neo4j indexing."""
        ctx = _make_ctx()
        ctx.parse_result = _FakeParseResult()
        ctx.doc_type = "document"
        ctx.document_type = "document"
        ctx.chunks = [
            _FakeChunk(
                chunk_index=0,
                text="Test chunk content",
                token_count=5,
                metadata={"page_number": 1, "section_heading": ""},
            ),
        ]
        ctx.embeddings = [[0.1, 0.2, 0.3]]
        ctx.sparse_embeddings = []
        ctx.all_entities = [{"name": "Test", "type": "PERSON", "page_number": 1}]

        mock_qdrant = MagicMock()

        with (
            patch("qdrant_client.QdrantClient", return_value=mock_qdrant),
            patch("app.ingestion.tasks._index_to_neo4j"),
            patch("app.ingestion.tasks.asyncio.run"),
        ):
            _stage_index(ctx)

        # Qdrant upsert was called
        mock_qdrant.upsert.assert_called_once()
        # Neo4j data was prepared
        assert len(ctx.chunk_data_for_neo4j) == 1
        assert ctx.chunk_data_for_neo4j[0]["text_preview"] == "Test chunk content"


class TestStageComplete:
    """Tests for _stage_complete."""

    def test_creates_document_record(self):
        """_stage_complete should create a document record and update stage."""
        ctx = _make_ctx()
        ctx.parse_result = _FakeParseResult()
        ctx.doc_type = "document"
        ctx.document_type = "document"
        ctx.chunks = [_FakeChunk(chunk_index=0, text="chunk", token_count=5)]
        ctx.all_entities = [{"name": "Test", "type": "PERSON", "page_number": 1}]
        ctx.embeddings = [[0.1, 0.2]]
        ctx.file_size = 100
        ctx.content_hash = "abc123"

        with (
            patch("app.ingestion.tasks._create_document_record", return_value="doc-001") as mock_create,
            patch("app.ingestion.tasks._update_stage"),
            patch("app.ingestion.tasks.detect_duplicates"),
            patch("app.entities.tasks.resolve_entities") as mock_resolve,
        ):
            mock_resolve.delay = MagicMock()
            _stage_complete(ctx)

        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args
        assert call_kwargs.kwargs["job_id"] == "job-001"
        assert call_kwargs.kwargs["filename"] == "test.pdf"


# ---------------------------------------------------------------------------
# ZIP helper tests
# ---------------------------------------------------------------------------


class TestShouldSkipZipMember:
    """Tests for _should_skip_zip_member."""

    def test_directories_return_true(self):
        assert _should_skip_zip_member("some_dir/") is True
        assert _should_skip_zip_member("nested/dir/") is True

    def test_macosx_and_ds_store_return_true(self):
        assert _should_skip_zip_member("__MACOSX/._file.pdf") is True
        assert _should_skip_zip_member(".DS_Store") is True
        assert _should_skip_zip_member("subdir/.DS_Store") is True

    def test_dotfiles_return_true(self):
        assert _should_skip_zip_member(".hidden_file") is True
        assert _should_skip_zip_member("subdir/.gitkeep") is True

    def test_nested_zip_returns_true(self):
        assert _should_skip_zip_member("inner.zip") is True
        assert _should_skip_zip_member("subdir/archive.zip") is True

    def test_valid_files_return_false(self):
        assert _should_skip_zip_member("document.pdf") is False
        assert _should_skip_zip_member("subdir/report.docx") is False
        assert _should_skip_zip_member("notes.txt") is False
        assert _should_skip_zip_member("data.csv") is False


class TestProcessZipMember:
    """Tests for _process_zip_member."""

    def test_returns_child_id_for_supported_file(self):
        """Should upload, create child job, dispatch, and return child_id."""
        mock_engine = MagicMock()
        mock_zf = MagicMock()
        mock_zf.read.return_value = b"file content"
        mock_settings = _make_mock_settings()

        with (
            patch("app.ingestion.tasks._upload_to_minio"),
            patch("app.ingestion.tasks._create_child_job", return_value="child-001") as mock_child,
            patch("app.ingestion.tasks.process_document") as mock_pd,
            patch("app.ingestion.parser.PARSER_ROUTES", {".pdf": "docling"}),
        ):
            mock_pd.delay = MagicMock()
            result = _process_zip_member(
                engine=mock_engine,
                zip_ref=mock_zf,
                member="report.pdf",
                job_id="job-001",
                matter_id="matter-001",
                minio_path_prefix="raw/job-001",
                child_index=0,
                settings=mock_settings,
            )

        assert result == "child-001"
        mock_child.assert_called_once()
        mock_pd.delay.assert_called_once()

    def test_returns_none_for_unsupported_extension(self):
        """Should return None for files with unsupported extensions."""
        mock_engine = MagicMock()
        mock_zf = MagicMock()
        mock_settings = _make_mock_settings()

        with patch("app.ingestion.parser.PARSER_ROUTES", {".pdf": "docling"}):
            result = _process_zip_member(
                engine=mock_engine,
                zip_ref=mock_zf,
                member="file.xyz",
                job_id="job-001",
                matter_id=None,
                minio_path_prefix="raw/job-001",
                child_index=0,
                settings=mock_settings,
            )

        assert result is None
