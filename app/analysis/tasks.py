"""Celery tasks for sentiment analysis and hot document detection.

Follows the same sync engine + asyncio.run() pattern as
``app/ingestion/tasks.py``.
"""

from __future__ import annotations

import asyncio
import json
from uuid import uuid4

import structlog
from celery import shared_task
from sqlalchemy import create_engine, text

from workers.celery_app import celery_app  # noqa: F401 — ensures @shared_task binds to our app

logger = structlog.get_logger(__name__)


def _get_sync_engine():
    """Create a disposable sync SQLAlchemy engine for the current task."""
    from app.config import Settings

    settings = Settings()
    return create_engine(settings.postgres_url_sync, pool_pre_ping=True)


def _create_job_sync(
    engine,
    matter_id: str | None,
    task_type: str,
    label: str,
    parent_job_id: str | None = None,
) -> str:
    """Insert a job row synchronously and return the job_id string."""
    job_id = str(uuid4())
    with engine.connect() as conn:
        conn.execute(
            text(
                """
                INSERT INTO jobs (id, status, stage, progress, task_type, label,
                                  matter_id, parent_job_id, created_at, updated_at)
                VALUES (:id, 'pending', 'starting', '{}', :task_type, :label,
                        :matter_id, :parent_job_id, now(), now())
                """
            ),
            {
                "id": job_id,
                "task_type": task_type,
                "label": label,
                "matter_id": matter_id,
                "parent_job_id": parent_job_id,
            },
        )
        conn.commit()
    return job_id


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


@shared_task(
    bind=True,
    name="analysis.scan_document_sentiment",
    max_retries=2,
    default_retry_delay=60,
    acks_late=True,
)
def scan_document_sentiment(self, doc_id: str, matter_id: str = "") -> dict:
    """Score a single document for sentiment, hot-doc signals, and anomalies.

    Steps:
    1. Fetch chunk texts from Qdrant and concatenate.
    2. Run sentiment scoring via LLM (Instructor).
    3. For emails, run completeness analysis with thread context.
    4. Optionally compute anomaly score against sender baseline.
    5. Persist results to PostgreSQL and propagate scores to Qdrant.
    """
    from app.config import Settings

    settings = Settings()
    engine = _get_sync_engine()

    structlog.contextvars.bind_contextvars(
        task_name="scan_document_sentiment",
        doc_id=doc_id,
        matter_id=matter_id,
    )
    logger.info("analysis.sentiment.start")

    job_id = _create_job_sync(
        engine,
        matter_id or None,
        "analysis_sentiment",
        f"Sentiment: {doc_id[:8]}...",
    )

    try:
        # -----------------------------------------------------------------
        # 1. Fetch chunk texts from Qdrant
        # -----------------------------------------------------------------
        _update_stage(engine, job_id, "loading_chunks", "processing")

        from qdrant_client import QdrantClient
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        from app.common.vector_store import TEXT_COLLECTION

        qdrant = QdrantClient(url=settings.qdrant_url)

        scroll_filter = Filter(must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))])
        points, _ = qdrant.scroll(
            collection_name=TEXT_COLLECTION,
            scroll_filter=scroll_filter,
            limit=20,
            with_payload=True,
            with_vectors=False,
        )

        if not points:
            logger.warning("analysis.sentiment.no_chunks")
            _update_stage(engine, job_id, "complete", "complete", progress={"skipped": True})
            return {"doc_id": doc_id, "status": "skipped", "reason": "no_chunks"}

        # Sort by chunk_index and concatenate
        sorted_points = sorted(points, key=lambda p: p.payload.get("chunk_index", 0))
        full_text = "\n".join(p.payload.get("chunk_text", "") for p in sorted_points)
        truncated_text = full_text[:8000]

        # -----------------------------------------------------------------
        # 2. Sentiment scoring via LLM
        # -----------------------------------------------------------------
        _update_stage(engine, job_id, "scoring", "processing")

        from app.analysis.sentiment import SentimentScorer
        from app.llm_config.resolver import resolve_llm_config_sync

        config = resolve_llm_config_sync("analysis", engine)
        scorer = SentimentScorer(
            api_key=config.api_key,
            model=config.model,
            provider=config.provider,
        )
        result = asyncio.run(scorer.score_document(truncated_text))

        # -----------------------------------------------------------------
        # 3. Completeness analysis for emails
        # -----------------------------------------------------------------
        completeness_result = None
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT document_type, metadata_ FROM documents WHERE id = :doc_id"),
                {"doc_id": doc_id},
            ).first()

        doc_type = row.document_type if row else ""
        metadata = {}
        if row and row.metadata_:
            metadata = json.loads(row.metadata_) if isinstance(row.metadata_, str) else row.metadata_

        if doc_type in ("eml", "msg"):
            from app.analysis.completeness import CompletenessAnalyzer

            thread_id = metadata.get("thread_id", "")
            thread_context = ""

            if thread_id:
                with engine.connect() as conn:
                    siblings = conn.execute(
                        text(
                            """
                            SELECT id, metadata_->>'subject' AS subject
                            FROM documents
                            WHERE matter_id = :mid
                              AND metadata_->>'thread_id' = :tid
                              AND id != :doc_id
                            ORDER BY created_at
                            LIMIT 5
                            """
                        ),
                        {"mid": matter_id, "tid": thread_id, "doc_id": doc_id},
                    ).all()

                # Build thread context from sibling chunk texts
                sibling_texts = []
                for sib in siblings:
                    sib_points, _ = qdrant.scroll(
                        collection_name=TEXT_COLLECTION,
                        scroll_filter=Filter(
                            must=[
                                FieldCondition(
                                    key="doc_id",
                                    match=MatchValue(value=str(sib.id)),
                                )
                            ]
                        ),
                        limit=5,
                        with_payload=True,
                        with_vectors=False,
                    )
                    for sp in sorted(sib_points, key=lambda p: p.payload.get("chunk_index", 0)):
                        sibling_texts.append(sp.payload.get("chunk_text", ""))

                thread_context = "\n---\n".join(sibling_texts)[:4000]

            analyzer = CompletenessAnalyzer(
                api_key=config.api_key,
                model=config.model,
                provider=config.provider,
            )
            completeness_result = asyncio.run(analyzer.analyze(truncated_text, thread_context))

        # -----------------------------------------------------------------
        # 4. Anomaly detection (best-effort)
        # -----------------------------------------------------------------
        anomaly_result = None
        sender = metadata.get("from", "")
        if sender and matter_id:
            try:
                from app.analysis.anomaly import CommunicationBaseline

                baseline = CommunicationBaseline.compute_baseline(engine, matter_id, sender)
                if baseline.message_count >= 3:
                    anomaly_result = CommunicationBaseline.compute_anomaly_score(result.sentiment, baseline)
            except Exception:
                logger.warning("analysis.anomaly.skipped", exc_info=True)

        # -----------------------------------------------------------------
        # 5. Persist to PostgreSQL
        # -----------------------------------------------------------------
        _update_stage(engine, job_id, "persisting", "processing")

        sentiment = result.sentiment
        update_params: dict = {
            "doc_id": doc_id,
            "sentiment_positive": sentiment.positive,
            "sentiment_negative": sentiment.negative,
            "sentiment_pressure": sentiment.pressure,
            "sentiment_opportunity": sentiment.opportunity,
            "sentiment_rationalization": sentiment.rationalization,
            "sentiment_intent": sentiment.intent,
            "sentiment_concealment": sentiment.concealment,
            "hot_doc_score": result.hot_doc_score,
            "context_gap_score": completeness_result.context_gap_score if completeness_result else None,
            "context_gaps": (
                json.dumps([g.model_dump() for g in completeness_result.gaps]) if completeness_result else None
            ),
            "anomaly_score": anomaly_result.anomaly_score if anomaly_result else None,
        }

        with engine.connect() as conn:
            conn.execute(
                text(
                    """
                    UPDATE documents SET
                        sentiment_positive = :sentiment_positive,
                        sentiment_negative = :sentiment_negative,
                        sentiment_pressure = :sentiment_pressure,
                        sentiment_opportunity = :sentiment_opportunity,
                        sentiment_rationalization = :sentiment_rationalization,
                        sentiment_intent = :sentiment_intent,
                        sentiment_concealment = :sentiment_concealment,
                        hot_doc_score = :hot_doc_score,
                        context_gap_score = :context_gap_score,
                        context_gaps = CAST(:context_gaps AS jsonb),
                        anomaly_score = :anomaly_score,
                        updated_at = now()
                    WHERE id = :doc_id
                    """
                ),
                update_params,
            )
            conn.commit()

        # -----------------------------------------------------------------
        # 6. Propagate key scores to Qdrant payload
        # -----------------------------------------------------------------
        qdrant_payload = {"hot_doc_score": result.hot_doc_score}
        if anomaly_result:
            qdrant_payload["anomaly_score"] = anomaly_result.anomaly_score

        qdrant.set_payload(
            collection_name=TEXT_COLLECTION,
            payload=qdrant_payload,
            points=scroll_filter,
        )

        _update_stage(
            engine,
            job_id,
            "complete",
            "complete",
            progress={"hot_doc_score": result.hot_doc_score},
        )

        logger.info(
            "analysis.sentiment.complete",
            hot_doc_score=result.hot_doc_score,
            anomaly_score=anomaly_result.anomaly_score if anomaly_result else None,
        )

        return {
            "doc_id": doc_id,
            "status": "complete",
            "hot_doc_score": result.hot_doc_score,
            "anomaly_score": anomaly_result.anomaly_score if anomaly_result else None,
        }

    except Exception as exc:
        _update_stage(engine, job_id, "failed", "failed", error=str(exc))
        logger.error("analysis.sentiment.failed", error=str(exc), exc_info=True)
        raise self.retry(exc=exc)


@shared_task(bind=True, name="analysis.scan_matter_hot_docs")
def scan_matter_hot_docs(self, matter_id: str) -> dict:
    """Dispatch sentiment scanning for all unscored documents in a matter.

    Queries for documents that have not yet been scored (hot_doc_score IS NULL)
    and dispatches individual ``scan_document_sentiment`` tasks for each.
    """
    engine = _get_sync_engine()

    structlog.contextvars.bind_contextvars(
        task_name="scan_matter_hot_docs",
        matter_id=matter_id,
    )
    logger.info("analysis.matter_scan.start")

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT id FROM documents
                WHERE matter_id = :mid
                  AND hot_doc_score IS NULL
                ORDER BY created_at
                """
            ),
            {"mid": matter_id},
        ).all()

    count = len(rows)
    parent_job_id = _create_job_sync(
        engine,
        matter_id,
        "analysis_matter_scan",
        f"Hot doc scan: {count} documents",
    )
    _update_stage(engine, parent_job_id, "querying_documents", "processing")

    dispatched = 0
    for row in rows:
        scan_document_sentiment.delay(str(row.id), matter_id)
        dispatched += 1

    _update_stage(
        engine,
        parent_job_id,
        "complete",
        "complete",
        progress={"dispatched": dispatched, "total": count},
    )

    logger.info("analysis.matter_scan.dispatched", count=dispatched)
    return {"matter_id": matter_id, "dispatched": dispatched}
