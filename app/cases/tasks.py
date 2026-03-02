"""Celery task for the Case Setup Agent.

Wraps the LangGraph case setup agent in a Celery task, following
the same pattern as ``app/ingestion/tasks.py``.
"""

from __future__ import annotations

import json
import traceback

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


def _update_stage(
    engine,
    job_id: str,
    stage: str,
    status: str,
    error: str | None = None,
) -> None:
    """Update a job's stage and status."""
    with engine.connect() as conn:
        conn.execute(
            text("""
                UPDATE jobs
                SET stage = :stage,
                    status = :status,
                    error = :error,
                    updated_at = now()
                WHERE id = :job_id
            """),
            {
                "job_id": job_id,
                "stage": stage,
                "status": status,
                "error": error,
            },
        )
        conn.commit()

    logger.info("case_setup.stage_updated", job_id=job_id, stage=stage, status=status)


def _update_case_context_status(engine, context_id: str, status: str) -> None:
    """Update case_contexts.status synchronously."""
    with engine.connect() as conn:
        conn.execute(
            text("""
                UPDATE case_contexts
                SET status = :status, updated_at = now()
                WHERE id = :context_id
            """),
            {"context_id": context_id, "status": status},
        )
        conn.commit()


def _write_results_to_db(engine, context_id: str, state: dict) -> None:
    """Write extracted claims, parties, terms, and timeline to PostgreSQL."""
    with engine.connect() as conn:
        # Write claims
        for claim in state.get("claims", []):
            conn.execute(
                text("""
                    INSERT INTO case_claims
                        (id, case_context_id, claim_number, claim_label, claim_text,
                         legal_elements, source_pages, created_at, updated_at)
                    VALUES
                        (gen_random_uuid(), :context_id, :claim_number, :claim_label,
                         :claim_text, :legal_elements, :source_pages, now(), now())
                """),
                {
                    "context_id": context_id,
                    "claim_number": claim["claim_number"],
                    "claim_label": claim["claim_label"],
                    "claim_text": claim["claim_text"],
                    "legal_elements": json.dumps(claim.get("legal_elements", [])),
                    "source_pages": json.dumps(claim.get("source_pages", [])),
                },
            )

        # Write parties
        for party in state.get("parties", []):
            conn.execute(
                text("""
                    INSERT INTO case_parties
                        (id, case_context_id, name, role, description, aliases,
                         source_pages, created_at, updated_at)
                    VALUES
                        (gen_random_uuid(), :context_id, :name, :role, :description,
                         :aliases, :source_pages, now(), now())
                """),
                {
                    "context_id": context_id,
                    "name": party["name"],
                    "role": party.get("role", "unknown"),
                    "description": party.get("description"),
                    "aliases": json.dumps(party.get("aliases", [])),
                    "source_pages": json.dumps(party.get("source_pages", [])),
                },
            )

        # Write defined terms
        for term in state.get("defined_terms", []):
            conn.execute(
                text("""
                    INSERT INTO case_defined_terms
                        (id, case_context_id, term, definition, source_pages,
                         created_at, updated_at)
                    VALUES
                        (gen_random_uuid(), :context_id, :term, :definition,
                         :source_pages, now(), now())
                """),
                {
                    "context_id": context_id,
                    "term": term["term"],
                    "definition": term["definition"],
                    "source_pages": json.dumps(term.get("source_pages", [])),
                },
            )

        # Write timeline
        timeline = state.get("timeline", [])
        if timeline:
            conn.execute(
                text("""
                    UPDATE case_contexts
                    SET timeline = CAST(:timeline AS jsonb), updated_at = now()
                    WHERE id = :context_id
                """),
                {
                    "context_id": context_id,
                    "timeline": json.dumps(timeline),
                },
            )

        conn.commit()


@shared_task(
    bind=True,
    name="cases.run_case_setup",
    max_retries=1,
    acks_late=True,
)
def run_case_setup(
    self,
    job_id: str,
    case_context_id: str,
    matter_id: str,
    minio_path: str,
) -> dict:
    """Run the Case Setup Agent as a Celery task.

    Stages: parsing -> extracting_claims -> extracting_parties
            -> extracting_terms -> building_timeline -> populating_graph -> complete
    """
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        task_id=self.request.id,
        job_id=job_id,
        case_context_id=case_context_id,
    )

    from app.config import Settings

    settings = Settings()
    engine = _get_sync_engine()

    logger.info("case_setup.start", minio_path=minio_path)

    try:
        _update_stage(engine, job_id, "parsing", "uploading")

        # Build the LangGraph graph and invoke
        from app.cases.agent import build_case_setup_graph

        llm_settings = {
            "api_key": settings.anthropic_api_key if settings.llm_provider == "anthropic" else settings.openai_api_key,
            "model": settings.llm_model,
            "provider": settings.llm_provider,
            "minio_endpoint": settings.minio_endpoint,
            "minio_access_key": settings.minio_access_key,
            "minio_secret_key": settings.minio_secret_key,
            "minio_bucket": settings.minio_bucket,
            "minio_use_ssl": settings.minio_use_ssl,
            "neo4j_uri": settings.neo4j_uri,
            "neo4j_user": settings.neo4j_user,
            "neo4j_password": settings.neo4j_password,
        }

        graph = build_case_setup_graph(llm_settings).compile()

        initial_state = {
            "matter_id": matter_id,
            "anchor_document_id": "",
            "case_context_id": case_context_id,
            "minio_path": minio_path,
            "document_text": "",
            "claims": [],
            "parties": [],
            "defined_terms": [],
            "timeline": [],
            "error": None,
        }

        # Invoke the graph synchronously (Celery worker)
        final_state = graph.invoke(initial_state)

        # Write results to PostgreSQL
        _update_stage(engine, job_id, "extracting_claims", "uploading")
        _write_results_to_db(engine, case_context_id, final_state)

        # Mark as draft (ready for lawyer review)
        _update_case_context_status(engine, case_context_id, "draft")

        _update_stage(engine, job_id, "complete", "complete")

        logger.info(
            "case_setup.complete",
            claims=len(final_state.get("claims", [])),
            parties=len(final_state.get("parties", [])),
            terms=len(final_state.get("defined_terms", [])),
            events=len(final_state.get("timeline", [])),
        )

        return {
            "job_id": job_id,
            "case_context_id": case_context_id,
            "status": "complete",
            "claims": len(final_state.get("claims", [])),
            "parties": len(final_state.get("parties", [])),
            "defined_terms": len(final_state.get("defined_terms", [])),
            "timeline_events": len(final_state.get("timeline", [])),
        }

    except Exception as exc:
        tb = traceback.format_exc()
        logger.error("case_setup.failed", error=str(exc), traceback=tb)

        try:
            _update_stage(engine, job_id, "failed", "failed", error=str(exc))
            _update_case_context_status(engine, case_context_id, "failed")
        except Exception:
            logger.error("case_setup.failed_to_update_status")

        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        raise

    finally:
        engine.dispose()
