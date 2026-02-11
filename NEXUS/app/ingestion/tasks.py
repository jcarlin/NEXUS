"""Celery tasks for the document ingestion pipeline.

Each task runs the full 6-stage pipeline defined in CLAUDE.md Section 5.1:

    uploading -> parsing -> chunking -> embedding -> extracting -> indexing -> complete

The Celery worker runs synchronously, so async operations (OpenAI embedding,
Neo4j graph writes) are dispatched via ``asyncio.run()``.  Each task creates
its own database connections and tears them down on completion.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import tempfile
import traceback
import uuid
from pathlib import Path

import structlog
from celery import shared_task
from sqlalchemy import create_engine, text

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Sync DB helpers (Celery tasks use the sync Postgres URL)
# ---------------------------------------------------------------------------

def _get_sync_engine():
    """Create a disposable sync SQLAlchemy engine for the current task."""
    from app.config import Settings

    settings = Settings()
    return create_engine(settings.postgres_url_sync, pool_pre_ping=True)


def _update_stage(
    engine,
    job_id: str,
    stage: str,
    status: str,
    progress: dict | None = None,
    error: str | None = None,
) -> None:
    """Update a job's stage, status, and progress in the ``jobs`` table."""
    with engine.connect() as conn:
        if progress is not None:
            conn.execute(
                text(
                    """
                    UPDATE jobs
                    SET stage = :stage,
                        status = :status,
                        progress = :progress::jsonb,
                        error = :error,
                        updated_at = now()
                    WHERE id = :job_id
                    """
                ),
                {
                    "job_id": job_id,
                    "stage": stage,
                    "status": status,
                    "progress": json.dumps(progress),
                    "error": error,
                },
            )
        else:
            conn.execute(
                text(
                    """
                    UPDATE jobs
                    SET stage = :stage,
                        status = :status,
                        error = :error,
                        updated_at = now()
                    WHERE id = :job_id
                    """
                ),
                {
                    "job_id": job_id,
                    "stage": stage,
                    "status": status,
                    "error": error,
                },
            )
        conn.commit()

    logger.info("task.stage_updated", job_id=job_id, stage=stage, status=status)


def _create_document_record(
    engine,
    job_id: str,
    filename: str,
    doc_type: str,
    page_count: int,
    chunk_count: int,
    entity_count: int,
    minio_path: str,
    file_size: int,
    content_hash: str,
) -> str:
    """Insert a row into the ``documents`` table and return its id."""
    doc_id = str(uuid.uuid4())
    with engine.connect() as conn:
        conn.execute(
            text(
                """
                INSERT INTO documents
                    (id, job_id, filename, document_type, page_count, chunk_count,
                     entity_count, minio_path, file_size_bytes, content_hash,
                     metadata_, created_at, updated_at)
                VALUES
                    (:id, :job_id, :filename, :doc_type, :page_count, :chunk_count,
                     :entity_count, :minio_path, :file_size, :content_hash,
                     :metadata_, now(), now())
                """
            ),
            {
                "id": doc_id,
                "job_id": job_id,
                "filename": filename,
                "doc_type": doc_type,
                "page_count": page_count,
                "chunk_count": chunk_count,
                "entity_count": entity_count,
                "minio_path": minio_path,
                "file_size": file_size,
                "content_hash": content_hash,
                "metadata_": "{}",
            },
        )
        conn.commit()

    logger.info("task.document_created", doc_id=doc_id, job_id=job_id, filename=filename)
    return doc_id


def _is_job_cancelled(engine, job_id: str) -> bool:
    """Check whether the job has been cancelled (status = 'failed' with error = 'Cancelled')."""
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT status, error FROM jobs WHERE id = :job_id"),
            {"job_id": job_id},
        )
        row = result.first()
        if row is None:
            return True
        return row.status == "failed"


# ---------------------------------------------------------------------------
# Sync MinIO helpers
# ---------------------------------------------------------------------------

def _download_from_minio(settings, minio_path: str) -> bytes:
    """Download an object from MinIO using a fresh boto3 client."""
    import boto3
    from botocore.config import Config as BotoConfig

    scheme = "https" if settings.minio_use_ssl else "http"
    endpoint_url = f"{scheme}://{settings.minio_endpoint}"

    client = boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=settings.minio_access_key,
        aws_secret_access_key=settings.minio_secret_key,
        config=BotoConfig(signature_version="s3v4"),
        region_name="us-east-1",
    )

    resp = client.get_object(Bucket=settings.minio_bucket, Key=minio_path)
    return resp["Body"].read()


def _upload_to_minio(settings, key: str, data: bytes, content_type: str = "image/png") -> None:
    """Upload bytes to MinIO using a fresh boto3 client."""
    import boto3
    from botocore.config import Config as BotoConfig

    scheme = "https" if settings.minio_use_ssl else "http"
    endpoint_url = f"{scheme}://{settings.minio_endpoint}"

    client = boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=settings.minio_access_key,
        aws_secret_access_key=settings.minio_secret_key,
        config=BotoConfig(signature_version="s3v4"),
        region_name="us-east-1",
    )

    client.put_object(
        Bucket=settings.minio_bucket,
        Key=key,
        Body=data,
        ContentType=content_type,
    )


# ---------------------------------------------------------------------------
# Async helpers (for embedding + Neo4j)
# ---------------------------------------------------------------------------

async def _embed_chunks(settings, chunk_texts: list[str]) -> list[list[float]]:
    """Embed chunk texts using the TextEmbedder (async OpenAI API)."""
    from app.ingestion.embedder import TextEmbedder

    embedder = TextEmbedder(
        api_key=settings.openai_api_key,
        model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
    )
    return await embedder.embed_texts(chunk_texts)


async def _index_to_neo4j(
    settings,
    doc_id: str,
    filename: str,
    doc_type: str,
    page_count: int,
    minio_path: str,
    entities: list[dict],
    chunk_data: list[dict],
) -> None:
    """Create Document, Entity, and Chunk nodes in Neo4j."""
    from neo4j import AsyncGraphDatabase

    from app.entities.graph_service import GraphService

    driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )
    try:
        gs = GraphService(driver)

        # Create document node
        await gs.create_document_node(
            doc_id=doc_id,
            filename=filename,
            doc_type=doc_type,
            page_count=page_count,
            minio_path=minio_path,
        )

        # Bulk-index entities
        if entities:
            await gs.index_entities_for_document(doc_id=doc_id, entities=entities)

        # Create chunk nodes
        for cd in chunk_data:
            await gs.create_chunk_node(
                chunk_id=cd["chunk_id"],
                text_preview=cd["text_preview"],
                page_number=cd.get("page_number", 1),
                qdrant_point_id=cd["qdrant_point_id"],
                doc_id=doc_id,
            )
    finally:
        await driver.close()


# ---------------------------------------------------------------------------
# Main Celery task
# ---------------------------------------------------------------------------

@shared_task(
    bind=True,
    name="ingestion.process_document",
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
    reject_on_worker_lost=True,
)
def process_document(self, job_id: str, minio_path: str) -> dict:
    """Run the full 6-stage ingestion pipeline for a single document.

    Stages:
        1. **Parsing**    — Download from MinIO, parse with Docling
        2. **Chunking**   — Semantic chunking with token limits
        3. **Embedding**  — OpenAI text-embedding-3-large (1024d)
        4. **Extracting** — GLiNER zero-shot NER
        5. **Indexing**   — Upsert to Qdrant + Neo4j
        6. **Complete**   — Mark job done, create document record

    Each stage updates the job row in Postgres so clients can poll progress.
    On failure, the job is marked ``failed`` with the error traceback.
    """
    from app.config import Settings

    settings = Settings()
    engine = _get_sync_engine()
    filename = minio_path.rsplit("/", 1)[-1]

    logger.info("task.start", job_id=job_id, minio_path=minio_path, filename=filename)

    try:
        # ---------------------------------------------------------------
        # Stage 1: PARSING — download file, parse with Docling
        # ---------------------------------------------------------------
        _update_stage(engine, job_id, "parsing", "uploading")

        file_bytes = _download_from_minio(settings, minio_path)
        content_hash = hashlib.sha256(file_bytes).hexdigest()[:16]
        file_size = len(file_bytes)

        logger.info("task.downloaded", job_id=job_id, size=file_size)

        # Write to temp file for parser
        suffix = Path(filename).suffix
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = Path(tmp.name)

        try:
            from app.ingestion.parser import DocumentParser

            parser = DocumentParser()
            parse_result = parser.parse(tmp_path, filename)
        finally:
            tmp_path.unlink(missing_ok=True)

        # Free file bytes from memory
        del file_bytes

        logger.info(
            "task.parsed",
            job_id=job_id,
            page_count=parse_result.page_count,
            text_length=len(parse_result.text),
        )

        # Store page images in MinIO for future ColQwen2.5
        doc_id_for_pages = job_id  # Use job_id as doc namespace for page images
        for page in parse_result.pages:
            for img_idx, img_bytes in enumerate(page.images):
                if img_bytes:
                    page_key = f"pages/{doc_id_for_pages}/page_{page.page_number:03d}_{img_idx}.png"
                    _upload_to_minio(settings, page_key, img_bytes)

        progress = {"pages_parsed": parse_result.page_count}
        _update_stage(engine, job_id, "chunking", "uploading", progress=progress)

        if _is_job_cancelled(engine, job_id):
            logger.warning("task.cancelled_during_processing", job_id=job_id)
            return {"job_id": job_id, "status": "cancelled"}

        # ---------------------------------------------------------------
        # Stage 2: CHUNKING — semantic chunking
        # ---------------------------------------------------------------
        from app.ingestion.chunker import TextChunker

        chunker = TextChunker(
            max_tokens=settings.chunk_size,
            overlap_tokens=settings.chunk_overlap,
        )
        chunks = chunker.chunk(
            parse_result.text,
            metadata={"source_file": filename},
        )

        logger.info("task.chunked", job_id=job_id, chunk_count=len(chunks))

        progress["chunks_created"] = len(chunks)
        _update_stage(engine, job_id, "embedding", "uploading", progress=progress)

        if _is_job_cancelled(engine, job_id):
            return {"job_id": job_id, "status": "cancelled"}

        # ---------------------------------------------------------------
        # Stage 3: EMBEDDING — OpenAI text-embedding-3-large (1024d)
        # ---------------------------------------------------------------
        chunk_texts = [c.text for c in chunks]

        if chunk_texts:
            embeddings = asyncio.run(_embed_chunks(settings, chunk_texts))
        else:
            embeddings = []

        logger.info("task.embedded", job_id=job_id, embedding_count=len(embeddings))

        progress["embeddings_generated"] = len(embeddings)
        _update_stage(engine, job_id, "extracting", "uploading", progress=progress)

        if _is_job_cancelled(engine, job_id):
            return {"job_id": job_id, "status": "cancelled"}

        # ---------------------------------------------------------------
        # Stage 4: EXTRACTING — GLiNER zero-shot NER
        # ---------------------------------------------------------------
        from app.entities.extractor import EntityExtractor

        extractor = EntityExtractor(model_name=settings.gliner_model)

        all_entities: list[dict] = []
        seen_entities: set[tuple[str, str]] = set()  # (name, type) dedup within doc

        for chunk in chunks:
            extracted = extractor.extract(chunk.text)
            for ent in extracted:
                key = (ent.text.strip().lower(), ent.type)
                if key not in seen_entities:
                    seen_entities.add(key)
                    all_entities.append({
                        "name": ent.text.strip(),
                        "type": ent.type,
                        "page_number": chunk.metadata.get("page_number"),
                    })

        logger.info(
            "task.entities_extracted",
            job_id=job_id,
            unique_entities=len(all_entities),
        )

        progress["entities_extracted"] = len(all_entities)
        _update_stage(engine, job_id, "indexing", "uploading", progress=progress)

        if _is_job_cancelled(engine, job_id):
            return {"job_id": job_id, "status": "cancelled"}

        # ---------------------------------------------------------------
        # Stage 5: INDEXING — Qdrant + Neo4j
        # ---------------------------------------------------------------
        # 5a. Qdrant upsert
        from qdrant_client import QdrantClient
        from qdrant_client.models import PointStruct

        qdrant = QdrantClient(url=settings.qdrant_url)

        points = []
        chunk_data_for_neo4j = []

        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            point_id = str(uuid.uuid4())
            points.append(
                PointStruct(
                    id=point_id,
                    vector=embedding,
                    payload={
                        "source_file": filename,
                        "page_number": chunk.metadata.get("page_number", 1),
                        "section_heading": chunk.metadata.get("section_heading", ""),
                        "chunk_text": chunk.text,
                        "chunk_index": chunk.chunk_index,
                        "doc_id": job_id,
                        "token_count": chunk.token_count,
                    },
                )
            )
            chunk_data_for_neo4j.append({
                "chunk_id": point_id,
                "text_preview": chunk.text[:200],
                "page_number": chunk.metadata.get("page_number", 1),
                "qdrant_point_id": point_id,
            })

        if points:
            from app.common.vector_store import TEXT_COLLECTION

            qdrant.upsert(collection_name=TEXT_COLLECTION, points=points)
            logger.info("task.qdrant_indexed", job_id=job_id, points=len(points))

        # 5b. Neo4j graph indexing
        doc_type = _infer_doc_type(filename)

        asyncio.run(
            _index_to_neo4j(
                settings=settings,
                doc_id=job_id,
                filename=filename,
                doc_type=doc_type,
                page_count=parse_result.page_count,
                minio_path=minio_path,
                entities=all_entities,
                chunk_data=chunk_data_for_neo4j,
            )
        )

        logger.info("task.neo4j_indexed", job_id=job_id, entities=len(all_entities))

        # ---------------------------------------------------------------
        # Stage 6: COMPLETE — create document record, mark job done
        # ---------------------------------------------------------------
        _create_document_record(
            engine=engine,
            job_id=job_id,
            filename=filename,
            doc_type=doc_type,
            page_count=parse_result.page_count,
            chunk_count=len(chunks),
            entity_count=len(all_entities),
            minio_path=minio_path,
            file_size=file_size,
            content_hash=content_hash,
        )

        _update_stage(
            engine,
            job_id,
            "complete",
            "complete",
            progress=progress,
        )

        logger.info(
            "task.complete",
            job_id=job_id,
            pages=parse_result.page_count,
            chunks=len(chunks),
            entities=len(all_entities),
            embeddings=len(embeddings),
        )

        return {
            "job_id": job_id,
            "status": "complete",
            "page_count": parse_result.page_count,
            "chunk_count": len(chunks),
            "entity_count": len(all_entities),
        }

    except Exception as exc:
        tb = traceback.format_exc()
        logger.error("task.failed", job_id=job_id, error=str(exc), traceback=tb)

        try:
            _update_stage(engine, job_id, "failed", "failed", error=str(exc))
        except Exception:
            logger.error("task.failed_to_update_status", job_id=job_id)

        # Let Celery retry on transient errors
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        raise

    finally:
        engine.dispose()


@shared_task(
    bind=True,
    name="ingestion.process_batch",
    max_retries=1,
    acks_late=True,
)
def process_batch(self, job_id: str, file_paths: list[str]) -> dict:
    """Orchestrate ingestion of a batch of files by spawning per-file subtasks.

    Not yet implemented — planned for M3.
    """
    raise NotImplementedError("Batch ingestion not yet implemented")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _infer_doc_type(filename: str) -> str:
    """Infer a broad document type from the filename extension."""
    ext = Path(filename).suffix.lower()
    type_map = {
        ".pdf": "document",
        ".docx": "document",
        ".doc": "document",
        ".xlsx": "spreadsheet",
        ".pptx": "presentation",
        ".html": "web_page",
        ".htm": "web_page",
        ".eml": "email",
        ".msg": "email",
        ".txt": "text",
        ".csv": "data",
        ".png": "image",
        ".jpg": "image",
        ".jpeg": "image",
        ".tiff": "image",
        ".tif": "image",
    }
    return type_map.get(ext, "other")
