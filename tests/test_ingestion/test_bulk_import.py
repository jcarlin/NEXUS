"""Tests for M12 bulk import: task, adapters, protocol, progress, HNSW, CLI."""

from __future__ import annotations

import textwrap
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient

from app.ingestion.bulk_import import DatasetAdapter, compute_content_hash

# ---------------------------------------------------------------------------
# 1. test_import_text_document_skips_parse
# ---------------------------------------------------------------------------


def test_import_text_document_skips_parse() -> None:
    """import_text_document should never call DocumentParser."""
    job_id = str(uuid4())
    text_content = "This is a test legal document about Acme Corp."
    filename = "test.txt"
    content_hash = compute_content_hash(text_content)

    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
    mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)
    mock_conn.execute = MagicMock()
    mock_conn.commit = MagicMock()

    mock_chunks = [
        MagicMock(
            text="chunk text",
            chunk_index=0,
            token_count=10,
            metadata={"page_number": 1, "section_heading": ""},
        )
    ]

    mock_chunker_cls = MagicMock()
    chunker_instance = mock_chunker_cls.return_value
    chunker_instance.chunk.return_value = mock_chunks

    mock_qdrant_cls = MagicMock()
    qdrant_instance = mock_qdrant_cls.return_value
    qdrant_instance.upsert = MagicMock()

    mock_extractor_cls = MagicMock()
    mock_entity = MagicMock(text="Acme Corp", type="ORG")
    mock_extractor_cls.return_value.extract.return_value = [mock_entity]

    with (
        patch("app.ingestion.tasks._get_sync_engine", return_value=mock_engine),
        patch("app.ingestion.tasks._update_stage"),
        patch("app.ingestion.tasks._store_celery_task_id"),
        patch("app.ingestion.tasks._upload_to_minio"),
        patch("app.ingestion.tasks._create_document_record", return_value=str(uuid4())),
        patch("app.ingestion.tasks.asyncio.run") as mock_arun,
        patch("app.ingestion.chunker.TextChunker", mock_chunker_cls),
        patch("qdrant_client.QdrantClient", mock_qdrant_cls),
        patch("app.entities.extractor.EntityExtractor", mock_extractor_cls),
        patch("app.ingestion.tasks.detect_duplicates"),
    ):
        # asyncio.run is called for _embed_chunks and _index_to_neo4j
        mock_arun.side_effect = [
            [[0.1] * 1024],  # _embed_chunks
            None,  # _index_to_neo4j
        ]

        from app.ingestion.tasks import import_text_document

        # Call the underlying run method directly (bypass Celery bind/self)
        result = import_text_document.run(
            job_id=job_id,
            text=text_content,
            filename=filename,
            content_hash=content_hash,
            matter_id=str(uuid4()),
        )

        assert result["status"] == "complete"
        assert result["chunk_count"] == 1

        # Key assertion: chunker was called with the raw text
        chunker_instance.chunk.assert_called_once()
        # Qdrant upsert was called
        qdrant_instance.upsert.assert_called_once()


# ---------------------------------------------------------------------------
# 1b. test_import_text_updates_qdrant_doc_id
# ---------------------------------------------------------------------------


def test_import_text_updates_qdrant_doc_id() -> None:
    """import_text_document must call _update_qdrant_doc_id to reconcile IDs."""
    job_id = str(uuid4())
    real_doc_id = str(uuid4())
    text_content = "Legal document text."
    filename = "test.txt"
    content_hash = compute_content_hash(text_content)

    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
    mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)
    mock_conn.execute = MagicMock()
    mock_conn.commit = MagicMock()

    mock_chunks = [
        MagicMock(
            text="chunk text",
            chunk_index=0,
            token_count=10,
            metadata={"page_number": 1, "section_heading": ""},
        )
    ]

    mock_chunker_cls = MagicMock()
    mock_chunker_cls.return_value.chunk.return_value = mock_chunks

    mock_qdrant_cls = MagicMock()
    mock_qdrant_cls.return_value.upsert = MagicMock()

    mock_extractor_cls = MagicMock()
    mock_extractor_cls.return_value.extract.return_value = []

    with (
        patch("app.ingestion.tasks._get_sync_engine", return_value=mock_engine),
        patch("app.ingestion.tasks._update_stage"),
        patch("app.ingestion.tasks._store_celery_task_id"),
        patch("app.ingestion.tasks._upload_to_minio"),
        patch("app.ingestion.tasks._create_document_record", return_value=real_doc_id),
        patch("app.ingestion.tasks.asyncio.run") as mock_arun,
        patch("app.ingestion.chunker.TextChunker", mock_chunker_cls),
        patch("qdrant_client.QdrantClient", mock_qdrant_cls),
        patch("app.entities.extractor.EntityExtractor", mock_extractor_cls),
        patch("app.ingestion.tasks.detect_duplicates"),
        patch("app.ingestion.tasks._update_qdrant_doc_id") as mock_update_doc_id,
    ):
        mock_arun.side_effect = [
            [[0.1] * 1024],  # _embed_chunks
            None,  # _index_to_neo4j
        ]

        from app.ingestion.tasks import import_text_document

        result = import_text_document.run(
            job_id=job_id,
            text=text_content,
            filename=filename,
            content_hash=content_hash,
            matter_id=str(uuid4()),
        )

        assert result["status"] == "complete"
        # _update_qdrant_doc_id must be called with qdrant_url, job_id, doc_id
        mock_update_doc_id.assert_called_once()
        call_args = mock_update_doc_id.call_args
        assert call_args[0][1] == job_id
        assert call_args[0][2] == real_doc_id


# ---------------------------------------------------------------------------
# 2. test_dataset_adapter_interface_contract
# ---------------------------------------------------------------------------


def test_dataset_adapter_interface_contract(tmp_path: Path) -> None:
    """All 3 adapters should satisfy the DatasetAdapter protocol."""
    from app.ingestion.adapters.concordance_dat import ConcordanceDATAdapter
    from app.ingestion.adapters.directory import DirectoryAdapter
    from app.ingestion.adapters.edrm_xml import EDRMXMLAdapter

    dir_adapter = DirectoryAdapter(data_dir=tmp_path)
    assert isinstance(dir_adapter, DatasetAdapter)

    # Create dummy files so adapters can be instantiated
    xml_file = tmp_path / "test.xml"
    xml_file.write_text("<EDRMExport></EDRMExport>")
    edrm_adapter = EDRMXMLAdapter(xml_path=xml_file)
    assert isinstance(edrm_adapter, DatasetAdapter)

    dat_file = tmp_path / "test.dat"
    dat_file.write_text("DOCID\n")
    dat_adapter = ConcordanceDATAdapter(dat_path=dat_file)
    assert isinstance(dat_adapter, DatasetAdapter)


# ---------------------------------------------------------------------------
# 3. test_directory_adapter_yields_documents
# ---------------------------------------------------------------------------


def test_directory_adapter_yields_documents(tmp_path: Path) -> None:
    """DirectoryAdapter should yield ImportDocument for .txt files recursively."""
    from app.ingestion.adapters.directory import DirectoryAdapter

    # Create test files (including nested subdir)
    (tmp_path / "doc1.txt").write_text("First document content")
    subdir = tmp_path / "subdir"
    subdir.mkdir()
    (subdir / "doc2.txt").write_text("Second document in subdir")
    (tmp_path / "ignored.pdf").write_text("not a text file")
    (tmp_path / ".DS_Store").write_text("os artifact")

    adapter = DirectoryAdapter(data_dir=tmp_path)
    docs = list(adapter.iter_documents())

    assert len(docs) == 2
    filenames = {d.filename for d in docs}
    assert filenames == {"doc1.txt", "doc2.txt"}

    # Verify ImportDocument fields
    for doc in docs:
        assert doc.source == "directory"
        assert doc.text
        assert len(doc.content_hash) == 16
        assert doc.metadata.get("relative_path")


# ---------------------------------------------------------------------------
# 4. test_edrm_adapter_parses_records
# ---------------------------------------------------------------------------


def test_edrm_adapter_parses_records(tmp_path: Path) -> None:
    """EDRMXMLAdapter should parse EDRM XML and yield ImportDocuments."""
    from app.ingestion.adapters.edrm_xml import EDRMXMLAdapter

    # Create text files
    (tmp_path / "doc001.txt").write_text("Legal document about the Acme Corp acquisition.")

    # Create EDRM XML
    xml_content = textwrap.dedent("""\
        <?xml version='1.0' encoding='utf-8'?>
        <EDRMExport>
          <Document DocID="DOC001">
            <File FilePath="doc001.txt">doc001.txt</File>
            <Tag TagName="Author" TagValue="John Smith" />
            <Tag TagName="Subject" TagValue="Acquisition" />
          </Document>
        </EDRMExport>
    """)
    xml_file = tmp_path / "loadfile.xml"
    xml_file.write_text(xml_content)

    adapter = EDRMXMLAdapter(xml_path=xml_file, content_dir=tmp_path)
    docs = list(adapter.iter_documents())

    assert len(docs) == 1
    assert docs[0].source_id == "DOC001"
    assert docs[0].filename == "doc001.txt"
    assert docs[0].source == "edrm_xml"
    assert "Acme Corp" in docs[0].text
    assert docs[0].metadata.get("Author") == "John Smith"


# ---------------------------------------------------------------------------
# 5. test_content_hash_dedup
# ---------------------------------------------------------------------------


def test_content_hash_dedup() -> None:
    """compute_content_hash should be deterministic and 16 chars long."""
    text = "The defendant entered into the agreement on January 15, 2024."

    hash1 = compute_content_hash(text)
    hash2 = compute_content_hash(text)

    assert hash1 == hash2
    assert len(hash1) == 16
    assert all(c in "0123456789abcdef" for c in hash1)

    # Different text should produce different hash
    hash3 = compute_content_hash("Different text entirely.")
    assert hash3 != hash1


# ---------------------------------------------------------------------------
# 6. test_dry_run_mode
# ---------------------------------------------------------------------------


def test_dry_run_mode(tmp_path: Path, capsys) -> None:
    """Dry-run should count documents and print estimates without dispatching."""
    # Create test files
    (tmp_path / "doc1.txt").write_text("Document one content" * 50)
    (tmp_path / "doc2.txt").write_text("Document two content" * 50)

    with patch(
        "sys.argv",
        [
            "import_dataset.py",
            "directory",
            "--data-dir",
            str(tmp_path),
            "--matter-id",
            str(uuid4()),
            "--dry-run",
        ],
    ):
        from scripts.import_dataset import main

        exit_code = main()

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Documents found:" in output
    assert "2" in output
    assert "Est. embedding cost:" in output


# ---------------------------------------------------------------------------
# 7. test_progress_tracking_endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_progress_tracking_endpoint(client: AsyncClient) -> None:
    """GET /bulk-imports/{id} should return BulkImportStatusResponse."""
    import_id = uuid4()
    matter_id = UUID("00000000-0000-0000-0000-000000000001")
    now = datetime.now(UTC)

    mock_row = {
        "id": import_id,
        "matter_id": matter_id,
        "adapter_type": "directory",
        "source_path": "/tmp/test",
        "status": "processing",
        "total_documents": 100,
        "processed_documents": 50,
        "failed_documents": 2,
        "skipped_documents": 3,
        "error": None,
        "created_at": now,
        "updated_at": now,
        "completed_at": None,
    }

    with patch(
        "app.ingestion.service.IngestionService.get_bulk_import_job",
        new_callable=AsyncMock,
        return_value=mock_row,
    ):
        response = await client.get(f"/api/v1/bulk-imports/{import_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["import_id"] == str(import_id)
    assert body["status"] == "processing"
    assert body["total_documents"] == 100
    assert body["processed_documents"] == 50
    assert body["failed_documents"] == 2
    assert body["skipped_documents"] == 3
    assert body["adapter_type"] == "directory"


@pytest.mark.asyncio
async def test_progress_tracking_endpoint_404(client: AsyncClient) -> None:
    """GET /bulk-imports/{id} should return 404 for non-existent job."""
    with patch(
        "app.ingestion.service.IngestionService.get_bulk_import_job",
        new_callable=AsyncMock,
        return_value=None,
    ):
        response = await client.get(f"/api/v1/bulk-imports/{uuid4()}")

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# 8. test_qdrant_hnsw_disable_rebuild
# ---------------------------------------------------------------------------


def test_qdrant_hnsw_disable_rebuild() -> None:
    """disable_hnsw_indexing/rebuild_hnsw_index should call update_collection."""
    from app.common.vector_store import VectorStoreClient

    mock_settings = MagicMock()
    mock_settings.qdrant_url = "http://localhost:6333"
    mock_settings.embedding_dimensions = 1024
    mock_settings.enable_visual_embeddings = False
    mock_settings.enable_sparse_embeddings = False

    with patch("app.common.vector_store.QdrantClient") as mock_client_cls:
        client = VectorStoreClient(mock_settings)
        qdrant_instance = mock_client_cls.return_value

        # Test disable
        client.disable_hnsw_indexing("nexus_text")
        qdrant_instance.update_collection.assert_called_once()
        call_kwargs = qdrant_instance.update_collection.call_args
        assert call_kwargs.kwargs["collection_name"] == "nexus_text"
        hnsw_config = call_kwargs.kwargs["hnsw_config"]
        assert hnsw_config.m == 0

        # Reset and test rebuild
        qdrant_instance.update_collection.reset_mock()
        client.rebuild_hnsw_index("nexus_text", m=16, ef_construct=200)
        qdrant_instance.update_collection.assert_called_once()
        call_kwargs = qdrant_instance.update_collection.call_args
        hnsw_config = call_kwargs.kwargs["hnsw_config"]
        assert hnsw_config.m == 16
        assert hnsw_config.ef_construct == 200


# ---------------------------------------------------------------------------
# 9. test_bulk_e2e_directory_import (integration)
# ---------------------------------------------------------------------------


def test_bulk_e2e_directory_import(tmp_path: Path) -> None:
    """Full directory import flow with all services mocked."""
    # Create test files
    for i in range(3):
        (tmp_path / f"doc{i}.txt").write_text(f"Document {i} content for testing")

    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
    mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)
    mock_conn.execute = MagicMock()
    mock_conn.commit = MagicMock()

    mock_task = MagicMock()
    mock_task.delay = MagicMock()

    with (
        patch("scripts.import_dataset._get_sync_engine", return_value=mock_engine),
        patch("app.ingestion.tasks.import_text_document", mock_task),
        patch("scripts.import_dataset.dispatch_post_ingestion_hooks", return_value=[]),
        patch(
            "sys.argv",
            [
                "import_dataset.py",
                "directory",
                "--data-dir",
                str(tmp_path),
                "--matter-id",
                str(uuid4()),
            ],
        ),
    ):
        from scripts.import_dataset import main

        exit_code = main()

    assert exit_code == 0
    assert mock_task.delay.call_count == 3


# ---------------------------------------------------------------------------
# 10. test_post_ingestion_trigger_queueing (integration)
# ---------------------------------------------------------------------------


def test_post_ingestion_trigger_queueing() -> None:
    """dispatch_post_ingestion_hooks should dispatch resolve_entities."""
    mock_celery_app = MagicMock()
    mock_celery_app.send_task = MagicMock()

    with patch("workers.celery_app.celery_app", mock_celery_app):
        from scripts.import_dataset import dispatch_post_ingestion_hooks

        matter_id = str(uuid4())
        dispatched = dispatch_post_ingestion_hooks(matter_id)

    assert "entities.resolve_entities" in dispatched
    assert "ingestion.detect_inclusive_emails" in dispatched

    # Verify send_task was called with expected task names
    call_names = [call.args[0] for call in mock_celery_app.send_task.call_args_list]
    assert "entities.resolve_entities" in call_names
