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
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog
from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy import create_engine, text

from workers.celery_app import celery_app  # noqa: F401 — ensures @shared_task binds to our app

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
                        progress = CAST(:progress AS jsonb),
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


def _store_celery_task_id(engine, job_id: str, celery_task_id: str) -> None:
    """Store the Celery task ID in the job row for revocation support."""
    with engine.connect() as conn:
        conn.execute(
            text(
                """
                UPDATE jobs
                SET celery_task_id = :celery_task_id,
                    updated_at = now()
                WHERE id = :job_id
                """
            ),
            {"job_id": job_id, "celery_task_id": celery_task_id},
        )
        conn.commit()


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
    matter_id: str | None = None,
    metadata: dict | None = None,
) -> str:
    """Insert a row into the ``documents`` table and return its id."""
    doc_id = str(uuid.uuid4())
    # Serialize metadata, stripping attachment_data (binary) if present
    meta = dict(metadata) if metadata else {}
    meta.pop("attachment_data", None)
    metadata_json = json.dumps(meta, default=str)
    with engine.connect() as conn:
        conn.execute(
            text(
                """
                INSERT INTO documents
                    (id, job_id, filename, document_type, page_count, chunk_count,
                     entity_count, minio_path, file_size_bytes, content_hash,
                     matter_id, metadata_, created_at, updated_at)
                VALUES
                    (:id, :job_id, :filename, :doc_type, :page_count, :chunk_count,
                     :entity_count, :minio_path, :file_size, :content_hash,
                     :matter_id, :metadata_, now(), now())
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
                "matter_id": matter_id,
                "metadata_": metadata_json,
            },
        )
        conn.commit()

    logger.info("task.document_created", doc_id=doc_id, job_id=job_id, filename=filename)
    return doc_id


def _create_child_job(
    engine,
    parent_job_id: str,
    filename: str,
    minio_path: str,
    matter_id: str | None = None,
) -> str:
    """Create a child job row linked to a parent (for ZIP / email attachments)."""
    child_id = str(uuid.uuid4())
    with engine.connect() as conn:
        conn.execute(
            text(
                """
                INSERT INTO jobs (id, filename, status, stage, progress, error,
                                  parent_job_id, matter_id, metadata_, created_at, updated_at)
                VALUES (:id, :filename, 'pending', 'uploading', '{}', NULL,
                        :parent_job_id, :matter_id, :metadata_, now(), now())
                """
            ),
            {
                "id": child_id,
                "filename": filename,
                "parent_job_id": parent_job_id,
                "matter_id": matter_id,
                "metadata_": json.dumps({"minio_path": minio_path}),
            },
        )
        conn.commit()

    logger.info(
        "task.child_job_created",
        child_id=child_id,
        parent_id=parent_job_id,
        filename=filename,
    )
    return child_id


def _get_job_matter_id(engine, job_id: str) -> str | None:
    """Read the matter_id from a job record (set at ingest time)."""
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT matter_id FROM jobs WHERE id = :job_id"),
            {"job_id": job_id},
        )
        row = result.first()
        if row is None or row.matter_id is None:
            return None
        return str(row.matter_id)


def _get_job_dataset_id(engine, job_id: str) -> str | None:
    """Read the dataset_id from a job record (set at ingest time)."""
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT dataset_id FROM jobs WHERE id = :job_id"),
            {"job_id": job_id},
        )
        row = result.first()
        if row is None or row.dataset_id is None:
            return None
        return str(row.dataset_id)


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
        return bool(row.status == "failed")


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
    return bytes(resp["Body"].read())


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
    """Embed chunk texts using the configured embedding provider."""
    from app.common.embedder import (
        EmbeddingProvider,
        LocalEmbeddingProvider,
        OpenAIEmbeddingProvider,
        TEIEmbeddingProvider,
    )

    provider: EmbeddingProvider
    if settings.embedding_provider == "local":
        provider = LocalEmbeddingProvider(
            model_name=settings.local_embedding_model,
            dimensions=settings.embedding_dimensions,
        )
    elif settings.embedding_provider == "tei":
        provider = TEIEmbeddingProvider(
            base_url=settings.tei_embedding_url,
            dimensions=settings.embedding_dimensions,
        )
    else:
        provider = OpenAIEmbeddingProvider(
            api_key=settings.openai_api_key,
            model=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
            batch_size=settings.embedding_batch_size,
        )
    return await provider.embed_texts(chunk_texts)


async def _index_to_neo4j(
    settings,
    doc_id: str,
    filename: str,
    doc_type: str,
    page_count: int,
    minio_path: str,
    entities: list[dict],
    chunk_data: list[dict],
    matter_id: str | None = None,
    email_metadata: dict | None = None,
) -> None:
    """Create Document, Entity, and Chunk nodes in Neo4j.

    When *email_metadata* is provided (for ``eml``/``msg`` files), also
    creates an ``:Email`` node and links participants via
    ``SENT`` / ``SENT_TO`` / ``CC`` / ``BCC`` edges.
    """
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
            matter_id=matter_id,
        )

        # Bulk-index entities (with dual labels + matter_id)
        if entities:
            await gs.index_entities_for_document(
                doc_id=doc_id,
                entities=entities,
                matter_id=matter_id,
            )

        # Create chunk nodes
        for cd in chunk_data:
            await gs.create_chunk_node(
                chunk_id=cd["chunk_id"],
                text_preview=cd["text_preview"],
                page_number=cd.get("page_number", 1),
                qdrant_point_id=cd["qdrant_point_id"],
                doc_id=doc_id,
            )

        # M11: Email-as-node modeling
        if email_metadata:
            from app.entities.schema import parse_email_address, parse_recipient_list

            email_id = email_metadata.get("message_id") or doc_id
            await gs.create_email_node(
                email_id=email_id,
                subject=email_metadata.get("subject", ""),
                date=email_metadata.get("date"),
                message_id=email_metadata.get("message_id"),
                doc_id=doc_id,
                matter_id=matter_id,
            )

            sender = None
            from_raw = email_metadata.get("from", "")
            if from_raw:
                sender = parse_email_address(from_raw)
                if not sender[1]:
                    sender = None

            to_list = parse_recipient_list(email_metadata.get("to", ""))
            cc_list = parse_recipient_list(email_metadata.get("cc", ""))
            bcc_list = parse_recipient_list(email_metadata.get("bcc", ""))

            if sender or to_list or cc_list or bcc_list:
                await gs.link_email_participants(
                    email_id=email_id,
                    sender=sender,
                    to=to_list,
                    cc=cc_list,
                    bcc=bcc_list,
                    matter_id=matter_id,
                )
    finally:
        await driver.close()


async def _extract_relationships(
    settings,
    doc_id: str,
    chunks,
    all_entities: list[dict],
) -> int:
    """Run Tier 2 relationship extraction (feature-flagged)."""
    from neo4j import AsyncGraphDatabase

    from app.entities.graph_service import GraphService
    from app.entities.relationship_extractor import RelationshipExtractor

    extractor = RelationshipExtractor(
        api_key=settings.anthropic_api_key,
        model=settings.llm_model,
        provider=settings.llm_provider,
    )
    driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )

    try:
        gs = GraphService(driver)
        total_rels = 0

        for chunk in chunks:
            # Find entities mentioned in this chunk
            chunk_entities = [e for e in all_entities if e["name"].lower() in chunk.text.lower()]
            if len(chunk_entities) < 2:
                continue

            relationships = await extractor.extract(chunk.text, chunk_entities)
            if relationships:
                rel_dicts = [r.model_dump() for r in relationships]
                count = await gs.create_relationships(doc_id, rel_dicts)
                total_rels += count

        return total_rels
    finally:
        await driver.close()


# ---------------------------------------------------------------------------
# Pipeline context (shared mutable state for stage functions)
# ---------------------------------------------------------------------------


@dataclass
class _PipelineContext:
    """Mutable state bag passed between pipeline stage functions.

    Populated incrementally: ``settings``, ``engine``, ``job_id``,
    ``minio_path``, ``filename``, and ``matter_id`` are set by the
    orchestrator before calling any stage.  Each stage then populates the
    remaining fields relevant to downstream stages.
    """

    # Set by orchestrator
    settings: Any
    engine: Any
    job_id: str
    minio_path: str
    filename: str
    matter_id: str | None
    dataset_id: str | None = None

    # Populated by _stage_parse
    parse_result: Any = None
    content_hash: str = ""
    file_size: int = 0
    doc_type: str = ""
    document_type: str = ""
    rendered_page_images: list[bytes] = field(default_factory=list)

    # Populated by _stage_chunk
    chunks: list[Any] = field(default_factory=list)

    # Populated by _stage_embed
    embeddings: list[list[float]] = field(default_factory=list)
    sparse_embeddings: list[tuple[list[int], list[float]]] = field(default_factory=list)
    visual_page_embeddings: list[dict[str, Any]] = field(default_factory=list)

    # Populated by _stage_extract
    all_entities: list[dict] = field(default_factory=list)
    relationship_count: int = 0

    # Populated by _stage_index
    chunk_data_for_neo4j: list[dict] = field(default_factory=list)

    # Progress dict shared across stages
    progress: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Pipeline stage functions
# ---------------------------------------------------------------------------


def _stage_parse(ctx: _PipelineContext) -> None:
    """Stage 1: Download from MinIO, parse, handle email attachments, render pages."""
    _update_stage(ctx.engine, ctx.job_id, "parsing", "processing")

    file_bytes = _download_from_minio(ctx.settings, ctx.minio_path)
    ctx.content_hash = hashlib.sha256(file_bytes).hexdigest()[:16]
    ctx.file_size = len(file_bytes)

    logger.info("task.downloaded", size=ctx.file_size)

    # Write to temp file for parser
    suffix = Path(ctx.filename).suffix
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = Path(tmp.name)

    try:
        from app.ingestion.parser import DocumentParser

        parser = DocumentParser()
        ctx.parse_result = parser.parse(tmp_path, ctx.filename)
    finally:
        tmp_path.unlink(missing_ok=True)

    # Free file bytes from memory
    del file_bytes

    logger.info(
        "task.parsed",
        page_count=ctx.parse_result.page_count,
        text_length=len(ctx.parse_result.text),
    )

    # Handle email attachments — spawn child jobs
    attachment_data = ctx.parse_result.metadata.get("attachment_data", [])
    if attachment_data:
        for att in attachment_data:
            att_filename = att["filename"]
            att_minio_path = f"raw/{ctx.job_id}/{att_filename}"
            _upload_to_minio(
                ctx.settings,
                att_minio_path,
                att["data"],
                content_type=att.get("content_type", "application/octet-stream"),
            )
            child_id = _create_child_job(ctx.engine, ctx.job_id, att_filename, att_minio_path, matter_id=ctx.matter_id)
            process_document.delay(child_id, att_minio_path)
            logger.info(
                "task.email_attachment_dispatched",
                parent_id=ctx.job_id,
                child_id=child_id,
                filename=att_filename,
            )

        # Strip binary attachment data from metadata before DB storage
        ctx.parse_result.metadata.pop("attachment_data", None)

    # Store page images in MinIO
    ext = Path(ctx.filename).suffix.lower()
    doc_id_for_pages = ctx.job_id
    ctx.rendered_page_images = []

    # Acceptable degradation: PDF page rendering is only needed for
    # visual embeddings (ENABLE_VISUAL_EMBEDDINGS), which is experimental.
    # Text-based indexing is the core pipeline and is unaffected.
    if ctx.settings.enable_visual_embeddings and ext == ".pdf":
        try:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as pdf_tmp:
                pdf_tmp.write(_download_from_minio(ctx.settings, ctx.minio_path))
                pdf_tmp_path = Path(pdf_tmp.name)
            try:
                ctx.rendered_page_images = _render_pdf_pages(str(pdf_tmp_path), dpi=ctx.settings.visual_page_dpi)
                for page_num, img_bytes in enumerate(ctx.rendered_page_images, 1):
                    page_key = f"pages/{doc_id_for_pages}/page_{page_num:03d}.png"
                    _upload_to_minio(ctx.settings, page_key, img_bytes)
                logger.info("task.pdf_pages_rendered", pages=len(ctx.rendered_page_images))
            finally:
                pdf_tmp_path.unlink(missing_ok=True)
        except Exception:
            logger.warning("task.pdf_page_rendering_failed", exc_info=True)
            ctx.rendered_page_images = []
    else:
        # Fallback: store Docling-provided page images (if any)
        for page in ctx.parse_result.pages:
            for img_idx, img_bytes in enumerate(page.images):
                if img_bytes:
                    page_key = f"pages/{doc_id_for_pages}/page_{page.page_number:03d}_{img_idx}.png"
                    _upload_to_minio(ctx.settings, page_key, img_bytes)

    ctx.progress["pages_parsed"] = ctx.parse_result.page_count
    _update_stage(ctx.engine, ctx.job_id, "chunking", "processing", progress=ctx.progress)


def _stage_chunk(ctx: _PipelineContext) -> None:
    """Stage 2: Semantic chunking + document type inference."""
    from app.ingestion.chunker import TextChunker

    chunker = TextChunker(
        max_tokens=ctx.settings.chunk_size,
        overlap_tokens=ctx.settings.chunk_overlap,
    )

    # Determine document type for format-specific chunking
    ctx.doc_type = _infer_doc_type(ctx.filename)
    ctx.document_type = ctx.parse_result.metadata.get("document_type", ctx.doc_type)

    ctx.chunks = chunker.chunk(
        ctx.parse_result.text,
        metadata={"source_file": ctx.filename},
        document_type=ctx.document_type,
    )

    logger.info("task.chunked", chunk_count=len(ctx.chunks))

    ctx.progress["chunks_created"] = len(ctx.chunks)
    _update_stage(ctx.engine, ctx.job_id, "embedding", "processing", progress=ctx.progress)


def _stage_embed(ctx: _PipelineContext) -> None:
    """Stage 3: Dense + sparse (feature-flagged) + visual (feature-flagged) embeddings."""
    chunk_texts = [c.text for c in ctx.chunks]

    if chunk_texts:
        ctx.embeddings = asyncio.run(_embed_chunks(ctx.settings, chunk_texts))
    else:
        ctx.embeddings = []

    # Sparse embeddings (feature-flagged)
    ctx.sparse_embeddings = []
    if ctx.settings.enable_sparse_embeddings and chunk_texts:
        from app.ingestion.sparse_embedder import SparseEmbedder

        sparse_emb = SparseEmbedder(model_name=ctx.settings.sparse_embedding_model)
        ctx.sparse_embeddings = sparse_emb.embed_texts(chunk_texts)
        logger.info("task.sparse_embedded", count=len(ctx.sparse_embeddings))

    # Visual embeddings (feature-flagged, experimental).
    # Acceptable degradation: visual embeddings are optional enrichment
    # that supplements text-based retrieval.
    ctx.visual_page_embeddings = []
    if ctx.settings.enable_visual_embeddings and ctx.rendered_page_images:
        try:
            import io

            from PIL import Image

            from app.ingestion.visual_embedder import VisualEmbedder

            visual_emb = VisualEmbedder(
                model_name=ctx.settings.visual_embedding_model,
                device=ctx.settings.visual_embedding_device,
            )

            # Identify visually complex pages
            complex_pages: list[tuple[int, bytes]] = []
            for page_idx, page_img_bytes in enumerate(ctx.rendered_page_images):
                page_num = page_idx + 1
                # Get page text (if available from parse result)
                page_text = ""
                has_tables = False
                for p in ctx.parse_result.pages:
                    if p.page_number == page_num:
                        page_text = p.text if hasattr(p, "text") else ""
                        has_tables = bool(getattr(p, "tables", []))
                        break

                if _is_visually_complex(page_text, ctx.filename, has_tables=has_tables):
                    complex_pages.append((page_num, page_img_bytes))

            # Batch embed visually complex pages
            if complex_pages:
                pil_images = [Image.open(io.BytesIO(img)) for _, img in complex_pages]
                batch_size = ctx.settings.visual_embedding_batch_size
                all_embeddings: list[list[list[float]]] = []

                for batch_start in range(0, len(pil_images), batch_size):
                    batch = pil_images[batch_start : batch_start + batch_size]
                    batch_embs = visual_emb.embed_images(batch)
                    all_embeddings.extend(batch_embs)

                for (page_num, _), emb in zip(complex_pages, all_embeddings):
                    point_id = f"{ctx.job_id}_page_{page_num}"
                    ctx.visual_page_embeddings.append(
                        {
                            "id": point_id,
                            "vectors": emb,
                            "payload": {
                                "doc_id": ctx.job_id,
                                "page_number": page_num,
                                "source_file": ctx.filename,
                                **({"matter_id": ctx.matter_id} if ctx.matter_id else {}),
                            },
                        }
                    )

                logger.info(
                    "task.visual_embedded",
                    complex_pages=len(complex_pages),
                    total_pages=len(ctx.rendered_page_images),
                )
        except Exception:
            logger.warning("task.visual_embedding_failed", exc_info=True)
            ctx.visual_page_embeddings = []

    logger.info("task.embedded", embedding_count=len(ctx.embeddings))

    ctx.progress["embeddings_generated"] = len(ctx.embeddings)
    _update_stage(ctx.engine, ctx.job_id, "extracting", "processing", progress=ctx.progress)


def _stage_extract(ctx: _PipelineContext) -> None:
    """Stage 4: GLiNER zero-shot NER + optional relationship extraction."""
    from app.entities.extractor import EntityExtractor

    extractor = EntityExtractor(model_name=ctx.settings.gliner_model)

    ctx.all_entities = []
    seen_entities: set[tuple[str, str]] = set()  # (name, type) dedup within doc

    for chunk in ctx.chunks:
        extracted = extractor.extract(chunk.text)
        for ent in extracted:
            key = (ent.text.strip().lower(), ent.type)
            if key not in seen_entities:
                seen_entities.add(key)
                ctx.all_entities.append(
                    {
                        "name": ent.text.strip(),
                        "type": ent.type,
                        "page_number": chunk.metadata.get("page_number"),
                    }
                )

    logger.info(
        "task.entities_extracted",
        unique_entities=len(ctx.all_entities),
    )

    # Tier 2: Relationship extraction (feature-flagged).
    # Acceptable degradation: relationship extraction is optional
    # enrichment via LLM (ENABLE_RELATIONSHIP_EXTRACTION).  Core
    # entity nodes and MENTIONED_IN edges are created regardless.
    ctx.relationship_count = 0
    if ctx.settings.enable_relationship_extraction and ctx.all_entities:
        try:
            ctx.relationship_count = asyncio.run(
                _extract_relationships(ctx.settings, ctx.job_id, ctx.chunks, ctx.all_entities)
            )
            logger.info(
                "task.relationships_extracted",
                count=ctx.relationship_count,
            )
        except Exception:
            logger.warning(
                "task.relationship_extraction_failed",
                exc_info=True,
            )

    ctx.progress["entities_extracted"] = len(ctx.all_entities)
    _update_stage(ctx.engine, ctx.job_id, "indexing", "processing", progress=ctx.progress)


def _stage_index(ctx: _PipelineContext) -> None:
    """Stage 5: Qdrant upsert (dense/sparse/visual) + Neo4j graph indexing."""
    # 5a. Qdrant upsert
    from qdrant_client import QdrantClient
    from qdrant_client.models import PointStruct, SparseVector

    qdrant = QdrantClient(url=ctx.settings.qdrant_url)

    points = []
    ctx.chunk_data_for_neo4j = []

    for i, (chunk, embedding) in enumerate(zip(ctx.chunks, ctx.embeddings)):
        point_id = str(uuid.uuid4())
        payload = {
            "source_file": ctx.filename,
            "page_number": chunk.metadata.get("page_number", 1),
            "section_heading": chunk.metadata.get("section_heading", ""),
            "chunk_text": chunk.text,
            "chunk_index": chunk.chunk_index,
            "doc_id": ctx.job_id,
            "token_count": chunk.token_count,
        }
        if ctx.matter_id is not None:
            payload["matter_id"] = ctx.matter_id

        # Build vector: named format when sparse enabled, unnamed otherwise
        vector: dict[str, Any] | list[float]
        if ctx.sparse_embeddings:
            indices, values = ctx.sparse_embeddings[i]
            vector = {
                "dense": embedding,
                "sparse": SparseVector(indices=indices, values=values),
            }
        elif ctx.settings.enable_sparse_embeddings:
            # Sparse enabled but no sparse vectors (e.g. empty text)
            vector = {"dense": embedding}
        else:
            vector = embedding

        points.append(PointStruct(id=point_id, vector=vector, payload=payload))
        ctx.chunk_data_for_neo4j.append(
            {
                "chunk_id": point_id,
                "text_preview": chunk.text[:200],
                "page_number": chunk.metadata.get("page_number", 1),
                "qdrant_point_id": point_id,
            }
        )

    if points:
        from app.common.vector_store import TEXT_COLLECTION

        qdrant.upsert(collection_name=TEXT_COLLECTION, points=points)
        logger.info("task.qdrant_indexed", points=len(points))

    # 5b. Visual Qdrant upsert (feature-flagged).
    # Acceptable degradation: visual index is optional; text index above
    # is the core data path.
    if ctx.visual_page_embeddings:
        try:
            from app.common.vector_store import VISUAL_COLLECTION

            vis_points = [
                PointStruct(id=vpe["id"], vector=vpe["vectors"], payload=vpe["payload"])
                for vpe in ctx.visual_page_embeddings
            ]
            qdrant.upsert(collection_name=VISUAL_COLLECTION, points=vis_points)
            logger.info("task.visual_indexed", pages=len(vis_points))
        except Exception:
            logger.warning("task.visual_indexing_failed", exc_info=True)

    # 5c. Neo4j graph indexing
    # M11: Pass email metadata for email-as-node modeling
    email_meta = None
    if ctx.document_type == "email":
        email_meta = {
            "message_id": ctx.parse_result.metadata.get("message_id", ""),
            "subject": ctx.parse_result.metadata.get("subject", ""),
            "date": ctx.parse_result.metadata.get("date"),
            "from": ctx.parse_result.metadata.get("from", ""),
            "to": ctx.parse_result.metadata.get("to", ""),
            "cc": ctx.parse_result.metadata.get("cc", ""),
            "bcc": ctx.parse_result.metadata.get("bcc", ""),
        }

    try:
        asyncio.run(
            _index_to_neo4j(
                settings=ctx.settings,
                doc_id=ctx.job_id,
                filename=ctx.filename,
                doc_type=ctx.doc_type,
                page_count=ctx.parse_result.page_count,
                minio_path=ctx.minio_path,
                entities=ctx.all_entities,
                chunk_data=ctx.chunk_data_for_neo4j,
                matter_id=ctx.matter_id,
                email_metadata=email_meta,
            )
        )
        logger.info("task.neo4j_indexed", entities=len(ctx.all_entities))
    except Exception:
        logger.error("task.neo4j_index_failed", doc_id=ctx.job_id, exc_info=True)


def _update_qdrant_doc_id(ctx: _PipelineContext, doc_id: str) -> None:
    """Update Qdrant payload to use real document ID instead of job_id placeholder."""
    from qdrant_client import QdrantClient
    from qdrant_client import models as qdrant_models

    try:
        client = QdrantClient(url=ctx.settings.qdrant_url)
        filter_ = qdrant_models.Filter(
            must=[
                qdrant_models.FieldCondition(
                    key="doc_id",
                    match=qdrant_models.MatchValue(value=ctx.job_id),
                )
            ]
        )

        from app.common.vector_store import TEXT_COLLECTION

        client.set_payload(
            collection_name=TEXT_COLLECTION,
            payload={"doc_id": doc_id},
            points=filter_,
        )

        if ctx.visual_page_embeddings:
            try:
                from app.common.vector_store import VISUAL_COLLECTION

                client.set_payload(
                    collection_name=VISUAL_COLLECTION,
                    payload={"doc_id": doc_id},
                    points=filter_,
                )
            except Exception:
                pass  # Visual collection may not exist

        client.close()
        logger.info("task.qdrant_doc_id_updated", job_id=ctx.job_id, doc_id=doc_id)
    except Exception:
        logger.warning("task.qdrant_doc_id_update_failed", job_id=ctx.job_id, exc_info=True)


def _stage_complete(ctx: _PipelineContext) -> None:
    """Stage 6: Create document record + dispatch post-processing tasks."""
    doc_id = _create_document_record(
        engine=ctx.engine,
        job_id=ctx.job_id,
        filename=ctx.filename,
        doc_type=ctx.doc_type,
        page_count=ctx.parse_result.page_count,
        chunk_count=len(ctx.chunks),
        entity_count=len(ctx.all_entities),
        minio_path=ctx.minio_path,
        file_size=ctx.file_size,
        content_hash=ctx.content_hash,
        matter_id=ctx.matter_id,
        metadata=ctx.parse_result.metadata,
    )

    # Update Qdrant payload with real document ID (was using job_id as placeholder)
    _update_qdrant_doc_id(ctx, doc_id)

    # Auto-assign document to dataset if the job has a dataset_id
    if ctx.dataset_id:
        with ctx.engine.connect() as conn:
            conn.execute(
                text("""
                    INSERT INTO dataset_documents (dataset_id, document_id)
                    VALUES (:dataset_id, :document_id)
                    ON CONFLICT DO NOTHING
                """),
                {"dataset_id": ctx.dataset_id, "document_id": doc_id},
            )
            conn.commit()
        logger.info("task.dataset_assigned", doc_id=doc_id, dataset_id=ctx.dataset_id)

    # Acceptable degradation: email threading is feature-flagged
    # post-processing that does not affect the core document record
    # or search index.  The document is fully ingested at this point.
    if ctx.document_type == "email" and ctx.settings.enable_email_threading:
        try:
            from app.ingestion.threading import EmailThreader

            email_headers = {
                "message_id": ctx.parse_result.metadata.get("message_id", ""),
                "in_reply_to": ctx.parse_result.metadata.get("in_reply_to", ""),
                "references": ctx.parse_result.metadata.get("references", ""),
                "subject": ctx.parse_result.metadata.get("subject", ""),
            }
            EmailThreader.assign_thread(ctx.engine, doc_id, email_headers, ctx.matter_id)
            logger.info("task.threading_complete", doc_id=doc_id)
        except Exception:
            logger.warning("task.threading_failed", exc_info=True)

    # Acceptable degradation: communication pair computation is incremental
    # post-processing for the analytics module.
    if ctx.document_type == "email" and ctx.matter_id:
        try:
            from app.analytics.service import AnalyticsService
            from app.dependencies import get_db

            async def _compute_pairs():
                async for db in get_db():
                    await AnalyticsService.compute_communication_pairs(db, ctx.matter_id)

            asyncio.run(_compute_pairs())
            logger.info("task.comm_pairs_updated", doc_id=doc_id)
        except Exception:
            logger.warning("task.comm_pairs_failed", exc_info=True)

    # Acceptable degradation: near-duplicate detection is a fire-and-forget
    # async task dispatch.  Failure to dispatch does not affect the document.
    if ctx.settings.enable_near_duplicate_detection:
        try:
            detect_duplicates.delay(doc_id, ctx.parse_result.text, ctx.matter_id or "")
            logger.info("task.dedup_dispatched", doc_id=doc_id)
        except Exception:
            logger.warning("task.dedup_dispatch_failed", exc_info=True)

    # Acceptable degradation: hot document detection is a fire-and-forget
    # async task dispatch (feature-flagged).
    if ctx.settings.enable_hot_doc_detection:
        try:
            from app.analysis.tasks import scan_document_sentiment

            scan_document_sentiment.delay(doc_id, ctx.matter_id or "")
            logger.info("task.hot_doc_dispatched", doc_id=doc_id)
        except Exception:
            logger.warning("task.hot_doc_dispatch_failed", exc_info=True)

    _update_stage(
        ctx.engine,
        ctx.job_id,
        "complete",
        "complete",
        progress=ctx.progress,
    )

    logger.info(
        "task.complete",
        pages=ctx.parse_result.page_count,
        chunks=len(ctx.chunks),
        entities=len(ctx.all_entities),
        embeddings=len(ctx.embeddings),
    )

    # Trigger entity resolution (async, non-blocking)
    from app.entities.tasks import resolve_entities

    resolve_entities.delay(matter_id=ctx.matter_id)


# ---------------------------------------------------------------------------
# ZIP helpers
# ---------------------------------------------------------------------------


def _should_skip_zip_member(member: str) -> bool:
    """Return True if the ZIP member should be skipped during extraction.

    Skips directories, OS artifacts (__MACOSX, .DS_Store, Thumbs.db),
    dotfiles, and nested ZIP archives.
    """
    # Directories
    if member.endswith("/"):
        return True

    # OS artifacts
    parts = Path(member).parts
    if any(p in _ZIP_SKIP_PATTERNS for p in parts):
        return True

    # Dotfiles
    basename = Path(member).name
    if basename.startswith("."):
        return True

    # Nested ZIPs
    ext = Path(basename).suffix.lower()
    if ext == ".zip":
        return True

    return False


def _process_zip_member(
    engine: Any,
    zip_ref: zipfile.ZipFile,
    member: str,
    job_id: str,
    matter_id: str | None,
    minio_path_prefix: str,
    child_index: int,
    settings: Any,
) -> str | None:
    """Extract a single file from the ZIP, upload to MinIO, and dispatch.

    Returns the child job ID on success, or None if the file type is
    unsupported.
    """
    from app.ingestion.parser import PARSER_ROUTES

    basename = Path(member).name
    ext = Path(basename).suffix.lower()

    backend = PARSER_ROUTES.get(ext)
    if backend is None or backend == "unsupported":
        logger.warning(
            "task.zip.unsupported_extension",
            job_id=job_id,
            member=member,
            ext=ext,
        )
        return None

    # Extract and upload to MinIO
    data = zip_ref.read(member)
    child_minio_path = f"raw/{job_id}/{basename}"
    _upload_to_minio(
        settings,
        child_minio_path,
        data,
        content_type="application/octet-stream",
    )

    # Create child job
    child_id = _create_child_job(engine, job_id, basename, child_minio_path, matter_id=matter_id)

    # Dispatch processing
    process_document.delay(child_id, child_minio_path)

    logger.info(
        "task.zip.child_dispatched",
        parent_id=job_id,
        child_id=child_id,
        filename=basename,
    )

    return child_id


# ---------------------------------------------------------------------------
# ZIP extraction task
# ---------------------------------------------------------------------------

# Files/dirs to skip when extracting ZIPs
_ZIP_SKIP_PATTERNS = {"__MACOSX", ".DS_Store", "Thumbs.db", ".gitkeep"}


@shared_task(
    bind=True,
    name="ingestion.process_zip",
    max_retries=1,
    acks_late=True,
)
def process_zip(self, job_id: str, minio_path: str) -> dict:
    """Extract a ZIP archive and dispatch child jobs for each file.

    - Skips __MACOSX/, .DS_Store, and other OS artifacts.
    - Checks each file extension against PARSER_ROUTES before dispatching.
    - Nested ZIPs are NOT recursed (single level).
    - Each extracted file gets its own child job linked via parent_job_id.
    """
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(task_id=self.request.id, job_id=job_id)

    from app.config import Settings

    settings = Settings()
    engine = _get_sync_engine()
    zip_matter_id = _get_job_matter_id(engine, job_id)
    structlog.contextvars.bind_contextvars(matter_id=zip_matter_id)

    try:
        _update_stage(engine, job_id, "parsing", "processing")

        file_bytes = _download_from_minio(settings, minio_path)

        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = Path(tmp.name)

        del file_bytes
        child_jobs: list[str] = []

        try:
            with zipfile.ZipFile(tmp_path, "r") as zf:
                for idx, member in enumerate(zf.namelist()):
                    if _should_skip_zip_member(member):
                        if Path(member).suffix.lower() == ".zip" and not member.endswith("/"):
                            logger.warning(
                                "task.zip.nested_zip_skipped",
                                member=member,
                            )
                        continue

                    child_id = _process_zip_member(
                        engine=engine,
                        zip_ref=zf,
                        member=member,
                        job_id=job_id,
                        matter_id=zip_matter_id,
                        minio_path_prefix=f"raw/{job_id}",
                        child_index=idx,
                        settings=settings,
                    )
                    if child_id is not None:
                        child_jobs.append(child_id)

        finally:
            tmp_path.unlink(missing_ok=True)

        _update_stage(
            engine,
            job_id,
            "complete",
            "complete",
            progress={"child_jobs": len(child_jobs)},
        )

        logger.info(
            "task.zip.complete",
            children=len(child_jobs),
        )

        return {
            "job_id": job_id,
            "status": "complete",
            "child_jobs": child_jobs,
        }

    except Exception as exc:
        logger.error("task.zip.failed", error=str(exc))

        # Acceptable degradation: if updating the job status itself fails,
        # the original error is still raised/retried below.
        try:
            _update_stage(engine, job_id, "failed", "failed", error=str(exc))
        except Exception:
            logger.error("task.zip.failed_to_update_status", exc_info=True)

        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        raise

    finally:
        engine.dispose()


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
        1. **Parsing**    — Download from MinIO, parse with Docling/EML/MSG/CSV/RTF
        2. **Chunking**   — Semantic chunking with token limits
        3. **Embedding**  — OpenAI text-embedding-3-large (1024d)
        4. **Extracting** — GLiNER zero-shot NER + optional relationship extraction
        5. **Indexing**   — Upsert to Qdrant + Neo4j
        6. **Complete**   — Mark job done, create document record

    Each stage updates the job row in Postgres so clients can poll progress.
    On failure, the job is marked ``failed`` with the error traceback.
    """
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(task_id=self.request.id, job_id=job_id)

    from app.config import Settings

    settings = Settings()
    engine = _get_sync_engine()
    _store_celery_task_id(engine, job_id, self.request.id)
    filename = minio_path.rsplit("/", 1)[-1]

    logger.info("task.start", minio_path=minio_path, filename=filename)

    # Read matter_id and dataset_id from the job record (set by the API router at ingest time)
    matter_id = _get_job_matter_id(engine, job_id)
    dataset_id = _get_job_dataset_id(engine, job_id)
    structlog.contextvars.bind_contextvars(matter_id=matter_id)

    # Detect ZIP files — delegate to process_zip
    ext = Path(filename).suffix.lower()
    if ext == ".zip":
        engine.dispose()
        return dict(process_zip(job_id, minio_path))

    ctx = _PipelineContext(
        settings=settings,
        engine=engine,
        job_id=job_id,
        minio_path=minio_path,
        filename=filename,
        matter_id=matter_id,
        dataset_id=dataset_id,
    )

    stages = [
        _stage_parse,
        _stage_chunk,
        _stage_embed,
        _stage_extract,
        _stage_index,
        _stage_complete,
    ]

    try:
        for stage_fn in stages:
            if _is_job_cancelled(engine, job_id):
                logger.warning("task.cancelled_during_processing")
                return {"job_id": job_id, "status": "cancelled"}
            stage_fn(ctx)

        return {
            "job_id": job_id,
            "status": "complete",
            "page_count": ctx.parse_result.page_count,
            "chunk_count": len(ctx.chunks),
            "entity_count": len(ctx.all_entities),
        }

    except SoftTimeLimitExceeded:
        logger.error("task.process_document.timeout", job_id=job_id)
        _update_stage(engine, job_id, "failed", "failed", error="Task timed out (soft time limit exceeded)")
        return {"job_id": job_id, "status": "failed", "error": "timeout"}

    except Exception as exc:
        tb = traceback.format_exc()
        logger.error("task.failed", error=str(exc), traceback=tb)

        # Acceptable degradation: if updating the job status itself fails,
        # the original error is still raised/retried below.
        try:
            _update_stage(engine, job_id, "failed", "failed", error=str(exc))
        except Exception:
            logger.error("task.failed_to_update_status", exc_info=True)

        # Let Celery retry on transient errors
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        raise

    finally:
        engine.dispose()


# ---------------------------------------------------------------------------
# Bulk import task (parse-skipping)
# ---------------------------------------------------------------------------


@shared_task(
    bind=True,
    name="ingestion.import_text_document",
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
    reject_on_worker_lost=True,
)
def import_text_document(
    self,
    job_id: str,
    text: str,
    filename: str,
    content_hash: str,
    matter_id: str | None = None,
    doc_type: str = "document",
    page_count: int = 1,
    metadata: dict | None = None,
    pre_entities: list[dict] | None = None,
    import_source: str | None = None,
    bulk_import_job_id: str | None = None,
    email_headers: dict | None = None,
) -> dict:
    """Import a pre-parsed text document, skipping the download+parse stage.

    Used by the bulk import system for pre-OCR'd text, load files, and
    directory-based imports.  Reuses the chunking, embedding, extraction,
    and indexing stages from ``process_document``.
    """
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(task_id=self.request.id, job_id=job_id, matter_id=matter_id)

    from app.config import Settings

    settings = Settings()
    from sqlalchemy import text as sa_text

    engine = _get_sync_engine()

    logger.info(
        "task.import_text.start",
        filename=filename,
        text_length=len(text),
    )

    try:
        # ---------------------------------------------------------------
        # Stage 1: UPLOAD — store raw text in MinIO for /documents/{id}/download
        # ---------------------------------------------------------------
        _update_stage(engine, job_id, "uploading", "uploading")

        minio_path = f"raw/{job_id}/{filename}"
        _upload_to_minio(settings, minio_path, text.encode("utf-8"), "text/plain")
        file_size = len(text.encode("utf-8"))

        logger.info("task.import_text.uploaded", minio_path=minio_path)

        # ---------------------------------------------------------------
        # Stage 2: CHUNKING
        # ---------------------------------------------------------------
        _update_stage(engine, job_id, "chunking", "processing")

        from app.ingestion.chunker import TextChunker

        chunker = TextChunker(
            max_tokens=settings.chunk_size,
            overlap_tokens=settings.chunk_overlap,
        )

        chunks = chunker.chunk(
            text,
            metadata={"source_file": filename},
            document_type=doc_type,
        )

        logger.info("task.import_text.chunked", chunk_count=len(chunks))

        progress: dict[str, Any] = {"chunks_created": len(chunks)}
        _update_stage(engine, job_id, "embedding", "processing", progress=progress)

        # ---------------------------------------------------------------
        # Stage 3: EMBEDDING — dense + optional sparse
        # ---------------------------------------------------------------
        chunk_texts = [c.text for c in chunks]

        if chunk_texts:
            embeddings = asyncio.run(_embed_chunks(settings, chunk_texts))
        else:
            embeddings = []

        sparse_embeddings: list[tuple[list[int], list[float]]] = []
        if settings.enable_sparse_embeddings and chunk_texts:
            from app.ingestion.sparse_embedder import SparseEmbedder

            sparse_emb = SparseEmbedder(model_name=settings.sparse_embedding_model)
            sparse_embeddings = sparse_emb.embed_texts(chunk_texts)

        logger.info("task.import_text.embedded", count=len(embeddings))

        progress["embeddings_generated"] = len(embeddings)
        _update_stage(engine, job_id, "extracting", "processing", progress=progress)

        # ---------------------------------------------------------------
        # Stage 4: EXTRACTING — use pre_entities or run GLiNER
        # ---------------------------------------------------------------
        all_entities: list[dict] = []

        if pre_entities:
            all_entities = pre_entities
        else:
            from app.entities.extractor import EntityExtractor

            extractor = EntityExtractor(model_name=settings.gliner_model)
            seen_entities: set[tuple[str, str]] = set()

            for chunk in chunks:
                extracted = extractor.extract(chunk.text)
                for ent in extracted:
                    key = (ent.text.strip().lower(), ent.type)
                    if key not in seen_entities:
                        seen_entities.add(key)
                        all_entities.append(
                            {
                                "name": ent.text.strip(),
                                "type": ent.type,
                                "page_number": chunk.metadata.get("page_number"),
                            }
                        )

        logger.info(
            "task.import_text.entities",
            entity_count=len(all_entities),
        )

        progress["entities_extracted"] = len(all_entities)
        _update_stage(engine, job_id, "indexing", "processing", progress=progress)

        # ---------------------------------------------------------------
        # Stage 5: INDEXING — Qdrant + Neo4j
        # ---------------------------------------------------------------
        from qdrant_client import QdrantClient
        from qdrant_client.models import PointStruct, SparseVector

        qdrant = QdrantClient(url=settings.qdrant_url)

        points = []
        chunk_data_for_neo4j = []

        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            point_id = str(uuid.uuid4())
            payload = {
                "source_file": filename,
                "page_number": chunk.metadata.get("page_number", 1),
                "section_heading": chunk.metadata.get("section_heading", ""),
                "chunk_text": chunk.text,
                "chunk_index": chunk.chunk_index,
                "doc_id": job_id,
                "token_count": chunk.token_count,
            }
            if matter_id is not None:
                payload["matter_id"] = matter_id

            vector: dict[str, Any] | list[float]
            if sparse_embeddings:
                indices, values = sparse_embeddings[i]
                vector = {
                    "dense": embedding,
                    "sparse": SparseVector(indices=indices, values=values),
                }
            elif settings.enable_sparse_embeddings:
                vector = {"dense": embedding}
            else:
                vector = embedding

            points.append(PointStruct(id=point_id, vector=vector, payload=payload))
            chunk_data_for_neo4j.append(
                {
                    "chunk_id": point_id,
                    "text_preview": chunk.text[:200],
                    "page_number": chunk.metadata.get("page_number", 1),
                    "qdrant_point_id": point_id,
                }
            )

        if points:
            from app.common.vector_store import TEXT_COLLECTION

            qdrant.upsert(collection_name=TEXT_COLLECTION, points=points)
            logger.info("task.import_text.qdrant_indexed", points=len(points))

        try:
            asyncio.run(
                _index_to_neo4j(
                    settings=settings,
                    doc_id=job_id,
                    filename=filename,
                    doc_type=doc_type,
                    page_count=page_count,
                    minio_path=minio_path,
                    entities=all_entities,
                    chunk_data=chunk_data_for_neo4j,
                    matter_id=matter_id,
                )
            )
            logger.info("task.neo4j_indexed", entities=len(all_entities))
        except Exception:
            logger.error("task.neo4j_index_failed", doc_id=job_id, exc_info=True)

        # ---------------------------------------------------------------
        # Stage 6: COMPLETE — document record + post-processing
        # ---------------------------------------------------------------
        doc_id = _create_document_record(
            engine=engine,
            job_id=job_id,
            filename=filename,
            doc_type=doc_type,
            page_count=page_count,
            chunk_count=len(chunks),
            entity_count=len(all_entities),
            minio_path=minio_path,
            file_size=file_size,
            content_hash=content_hash,
            matter_id=matter_id,
            metadata=metadata,
        )

        # Set import_source on the document record
        if import_source:
            with engine.connect() as conn:
                conn.execute(
                    sa_text("UPDATE documents SET import_source = :source WHERE id = :doc_id"),
                    {"source": import_source, "doc_id": doc_id},
                )
                conn.commit()

        # Acceptable degradation: email threading is feature-flagged
        # post-processing.  The document is fully ingested at this point.
        if email_headers and settings.enable_email_threading:
            try:
                from app.ingestion.threading import EmailThreader

                EmailThreader.assign_thread(engine, doc_id, email_headers, matter_id)
                logger.info("task.import_text.threading_complete")
            except Exception:
                logger.warning("task.import_text.threading_failed", exc_info=True)

        # Acceptable degradation: near-duplicate detection is a fire-and-forget
        # async task dispatch.
        if settings.enable_near_duplicate_detection:
            try:
                detect_duplicates.delay(doc_id, text, matter_id or "")
                logger.info("task.import_text.dedup_dispatched")
            except Exception:
                logger.warning("task.import_text.dedup_dispatch_failed", exc_info=True)

        # Acceptable degradation: hot document detection is a fire-and-forget
        # async task dispatch (feature-flagged).
        if settings.enable_hot_doc_detection:
            try:
                from app.analysis.tasks import scan_document_sentiment

                scan_document_sentiment.delay(doc_id, matter_id or "")
                logger.info("task.import_text.hot_doc_dispatched", doc_id=doc_id)
            except Exception:
                logger.warning("task.import_text.hot_doc_dispatch_failed", exc_info=True)

        # Increment bulk_import_jobs counter
        if bulk_import_job_id:
            with engine.connect() as conn:
                conn.execute(
                    sa_text(
                        """
                        UPDATE bulk_import_jobs
                        SET processed_documents = processed_documents + 1,
                            updated_at = now()
                        WHERE id = :id
                        """
                    ),
                    {"id": bulk_import_job_id},
                )
                conn.commit()

        _update_stage(engine, job_id, "complete", "complete", progress=progress)

        logger.info(
            "task.import_text.complete",
            chunks=len(chunks),
            entities=len(all_entities),
        )

        return {
            "job_id": job_id,
            "status": "complete",
            "page_count": page_count,
            "chunk_count": len(chunks),
            "entity_count": len(all_entities),
        }

    except Exception as exc:
        tb = traceback.format_exc()
        logger.error("task.import_text.failed", error=str(exc), traceback=tb)

        # Acceptable degradation: if updating the job status itself fails,
        # the original error is still raised/retried below.
        try:
            _update_stage(engine, job_id, "failed", "failed", error=str(exc))
        except Exception:
            logger.error("task.import_text.failed_to_update_status", exc_info=True)

        # Acceptable degradation: if updating the bulk import counter fails,
        # the individual job error is still raised/retried below.
        if bulk_import_job_id:
            try:
                with engine.connect() as conn:
                    conn.execute(
                        sa_text(
                            """
                            UPDATE bulk_import_jobs
                            SET failed_documents = failed_documents + 1,
                                updated_at = now()
                            WHERE id = :id
                            """
                        ),
                        {"id": bulk_import_job_id},
                    )
                    conn.commit()
            except Exception:
                logger.error("task.import_text.failed_to_update_bulk_job", exc_info=True)

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
# Near-duplicate detection task
# ---------------------------------------------------------------------------


@shared_task(
    bind=True,
    name="ingestion.detect_duplicates",
    max_retries=1,
    default_retry_delay=30,
    acks_late=True,
)
def detect_duplicates(self, doc_id: str, text: str, matter_id: str) -> dict:
    """Detect near-duplicate documents using MinHash + LSH.

    Runs asynchronously after document creation. Assigns duplicate
    cluster IDs and detects version groups.
    """
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(task_id=self.request.id, doc_id=doc_id, matter_id=matter_id)

    from app.config import Settings

    settings = Settings()
    engine = _get_sync_engine()

    try:
        if not settings.enable_near_duplicate_detection:
            return {"doc_id": doc_id, "status": "skipped", "reason": "disabled"}

        from app.ingestion.dedup import NearDuplicateDetector, VersionDetector

        detector = NearDuplicateDetector(
            threshold=settings.dedup_jaccard_threshold,
            num_perm=settings.dedup_num_permutations,
            shingle_size=settings.dedup_shingle_size,
        )

        matches = detector.find_duplicates(doc_id, text, matter_id or "default")

        cluster_id = None
        if matches:
            cluster_id = NearDuplicateDetector.assign_cluster(engine, doc_id, matches)

        # Version detection
        with engine.connect() as conn:
            from sqlalchemy import text as sa_text

            result = conn.execute(
                sa_text("SELECT filename FROM documents WHERE id = :doc_id"),
                {"doc_id": doc_id},
            )
            row = result.first()
            filename = row.filename if row else ""

        version_group_id = None
        if matches and filename:
            version_group_id = VersionDetector.detect_versions(
                engine,
                doc_id,
                filename,
                matches,
                version_upper_threshold=settings.dedup_version_upper_threshold,
            )

        logger.info(
            "task.detect_duplicates.complete",
            match_count=len(matches),
            cluster_id=cluster_id,
            version_group_id=version_group_id,
        )

        return {
            "doc_id": doc_id,
            "status": "complete",
            "match_count": len(matches),
            "cluster_id": cluster_id,
            "version_group_id": version_group_id,
        }

    except Exception as exc:
        logger.error("task.detect_duplicates.failed", error=str(exc))
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        raise
    finally:
        engine.dispose()


# ---------------------------------------------------------------------------
# Inclusive email detection task
# ---------------------------------------------------------------------------


@shared_task(
    bind=True,
    name="ingestion.detect_inclusive_emails",
    max_retries=1,
    default_retry_delay=30,
    acks_late=True,
)
def detect_inclusive_emails(self, matter_id: str | None = None) -> dict:
    """Mark inclusive emails in each thread.

    Post-batch task: should be run after all emails in a batch are ingested.
    """
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(task_id=self.request.id)

    from app.config import Settings

    settings = Settings()

    if not settings.enable_email_threading:
        return {"status": "skipped", "reason": "threading disabled"}

    engine = _get_sync_engine()

    try:
        from app.ingestion.threading import EmailThreader

        count = EmailThreader.detect_inclusive_emails(engine, matter_id)

        logger.info(
            "task.detect_inclusive.complete",
            inclusive_count=count,
            matter_id=matter_id,
        )

        return {
            "status": "complete",
            "inclusive_count": count,
            "matter_id": matter_id,
        }

    except Exception as exc:
        logger.error("task.detect_inclusive.failed", error=str(exc))
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        raise
    finally:
        engine.dispose()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _render_pdf_pages(file_path: str, dpi: int = 144) -> list[bytes]:
    """Render PDF pages to PNG bytes via pdf2image.

    Requires system ``poppler`` (``brew install poppler`` on macOS).

    Args:
        file_path: Path to the PDF file on disk.
        dpi: Resolution for rendering.

    Returns:
        List of PNG bytes, one per page.
    """
    import io

    from pdf2image import convert_from_path

    images = convert_from_path(file_path, dpi=dpi)
    page_bytes: list[bytes] = []
    for img in images:
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        page_bytes.append(buf.getvalue())
    return page_bytes


def _is_visually_complex(page_text: str, filename: str, has_tables: bool = False) -> bool:
    """Determine if a page should receive visual embeddings.

    A page is considered visually complex if any of:
      - It has tables
      - It has very little text (< 100 chars → likely a scan or chart)
      - The source file is a presentation or spreadsheet
    """
    ext = Path(filename).suffix.lower()
    if ext in (".pptx", ".xlsx"):
        return True
    if has_tables:
        return True
    if len(page_text.strip()) < 100:
        return True
    return False


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
        ".tsv": "data",
        ".rtf": "document",
        ".png": "image",
        ".jpg": "image",
        ".jpeg": "image",
        ".tiff": "image",
        ".tif": "image",
    }
    return type_map.get(ext, "other")


# ---------------------------------------------------------------------------
# Bulk import orchestrator task
# ---------------------------------------------------------------------------


@shared_task(
    bind=True,
    name="ingestion.run_bulk_import",
    acks_late=True,
    reject_on_worker_lost=True,
)
def run_bulk_import(
    self,
    bulk_job_id: str,
    adapter_type: str,
    source_config: dict,
    matter_id: str,
    dataset_id: str,
    options: dict,
) -> dict:
    """Orchestrate a bulk dataset import as a Celery task.

    Builds the appropriate adapter, iterates documents, creates job rows,
    and dispatches ``import_text_document`` subtasks for each document.
    """
    import uuid as _uuid

    import structlog

    from app.ingestion.bulk_import import (
        build_adapter,
        check_resume,
        complete_bulk_job,
        create_job_row,
        dispatch_post_ingestion_hooks,
        increment_skipped,
    )

    _logger = structlog.get_logger(__name__)
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        task_id=self.request.id,
        bulk_job_id=bulk_job_id,
        matter_id=matter_id,
    )

    resume = options.get("resume", False)
    limit = options.get("limit")
    disable_hnsw = options.get("disable_hnsw", False)

    engine = _get_sync_engine()
    qdrant_client = None

    try:
        # Build adapter
        adapter = build_adapter(adapter_type, source_config)

        # Disable HNSW if requested
        if disable_hnsw:
            from app.common.vector_store import (
                TEXT_COLLECTION,
                VectorStoreClient,
            )
            from app.config import Settings

            settings = Settings()
            qdrant_client = VectorStoreClient(settings)
            _logger.info("bulk_import.hnsw_disabled")
            qdrant_client.disable_hnsw_indexing(TEXT_COLLECTION)

        # Dispatch tasks
        dispatched = 0
        skipped = 0

        for doc in adapter.iter_documents(limit=limit):
            # Skip empty text
            if not doc.text.strip():
                skipped += 1
                increment_skipped(engine, bulk_job_id)
                continue

            # Resume: skip if content hash exists
            if resume and check_resume(
                engine,
                doc.content_hash,
                matter_id,
            ):
                skipped += 1
                increment_skipped(engine, bulk_job_id)
                continue

            # Create job row
            job_id = str(_uuid.uuid4())
            create_job_row(
                engine,
                job_id,
                doc.filename,
                matter_id,
                dataset_id,
            )

            # Dispatch per-document task
            import_text_document.delay(
                job_id=job_id,
                text=doc.text,
                filename=doc.filename,
                content_hash=doc.content_hash,
                matter_id=matter_id,
                doc_type=doc.doc_type,
                page_count=doc.page_count,
                metadata=doc.metadata,
                pre_entities=doc.entities if doc.entities else None,
                import_source=doc.source,
                bulk_import_job_id=bulk_job_id,
                email_headers=doc.email_headers,
            )

            dispatched += 1

        # Rebuild HNSW if it was disabled
        if disable_hnsw and qdrant_client:
            from app.common.vector_store import TEXT_COLLECTION

            _logger.info("bulk_import.hnsw_rebuilding")
            qdrant_client.rebuild_hnsw_index(TEXT_COLLECTION)

        # Dispatch post-ingestion hooks
        dispatched_hooks = dispatch_post_ingestion_hooks(matter_id)
        _logger.info(
            "bulk_import.hooks_dispatched",
            hooks=dispatched_hooks,
        )

        # Mark bulk job as dispatched (tasks still running in Celery)
        complete_bulk_job(engine, bulk_job_id, "complete")

        _logger.info(
            "bulk_import.complete",
            dispatched=dispatched,
            skipped=skipped,
        )

        return {
            "bulk_job_id": bulk_job_id,
            "dispatched": dispatched,
            "skipped": skipped,
            "status": "complete",
        }

    except Exception as exc:
        _logger.error(
            "bulk_import.failed",
            error=str(exc),
            exc_info=True,
        )
        complete_bulk_job(engine, bulk_job_id, "failed", str(exc))
        raise
    finally:
        engine.dispose()
