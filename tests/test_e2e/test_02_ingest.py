"""E2E tests for the ingestion pipeline.

Covers POST /api/v1/ingest, GET /api/v1/jobs/{job_id}, GET /api/v1/jobs,
and downstream side-effects (Postgres documents table, Qdrant points).

Celery runs in eager mode (task_always_eager=True), so the ingestion pipeline
executes synchronously within the POST /ingest request and the job is
complete by the time we poll.
"""

from __future__ import annotations

from io import BytesIO

import pytest
from httpx import AsyncClient

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

INGEST_URL = "/api/v1/ingest"
JOBS_URL = "/api/v1/jobs"
DOCUMENTS_URL = "/api/v1/documents"

QDRANT_URL = "http://localhost:6333"
QDRANT_COLLECTION = "nexus_text"


# ---------------------------------------------------------------------------
# Tests: ingest job lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.e2e
async def test_ingest_txt_creates_job(
    ingested_document: dict,
) -> None:
    """Ingesting a TXT file produces a job that completes successfully."""
    assert ingested_document["status"] == "complete", (
        f"Expected status 'complete', got: {ingested_document['status']}. "
        f"Error field: {ingested_document.get('error')}"
    )


@pytest.mark.e2e
async def test_ingest_job_has_correct_filename(
    ingested_document: dict,
) -> None:
    """The completed job reports the original filename."""
    assert (
        ingested_document["filename"] == "sample_legal_doc.txt"
    ), f"Unexpected filename: {ingested_document['filename']}"


@pytest.mark.e2e
async def test_ingest_progress_shows_counts(
    ingested_document: dict,
) -> None:
    """The completed job reports at least one chunk and a non-negative entity count."""
    progress = ingested_document.get("progress", {})
    chunks_created = progress.get("chunks_created", 0)
    entities_extracted = progress.get("entities_extracted", 0)

    assert chunks_created > 0, f"Expected chunks_created > 0, got {chunks_created}. " f"Full progress: {progress}"
    assert entities_extracted >= 0, f"entities_extracted must be non-negative, got {entities_extracted}"


@pytest.mark.e2e
async def test_list_jobs_includes_ingested(
    e2e_client: AsyncClient,
    admin_auth_headers: dict[str, str],
    ingested_document: dict,
) -> None:
    """GET /jobs returns a paginated list that contains at least one job."""
    resp = await e2e_client.get(JOBS_URL, headers=admin_auth_headers)

    assert resp.status_code == 200, f"List jobs failed: {resp.text}"
    data = resp.json()

    assert "items" in data, f"Response missing 'items' key: {data}"
    assert "total" in data, f"Response missing 'total' key: {data}"
    assert isinstance(data["items"], list), "'items' must be a list"
    assert data["total"] >= 1, f"Expected at least 1 job in list, total={data['total']}"

    job_ids = [item["job_id"] for item in data["items"]]
    assert (
        str(ingested_document["job_id"]) in job_ids
    ), f"Ingested job {ingested_document['job_id']} not found in job list: {job_ids}"


@pytest.mark.e2e
async def test_ingest_empty_file_rejected(
    e2e_client: AsyncClient,
    admin_auth_headers: dict[str, str],
) -> None:
    """Uploading an empty file is rejected with HTTP 400."""
    resp = await e2e_client.post(
        INGEST_URL,
        files={"file": ("empty.txt", BytesIO(b""), "text/plain")},
        headers=admin_auth_headers,
    )

    assert resp.status_code == 400, f"Expected 400 for empty file upload, got {resp.status_code}: {resp.text}"


# ---------------------------------------------------------------------------
# Tests: downstream side-effects
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.slow
async def test_ingest_creates_document_in_postgres(
    e2e_client: AsyncClient,
    admin_auth_headers: dict[str, str],
    ingested_document: dict,
) -> None:
    """After ingestion, the document appears in GET /documents."""
    resp = await e2e_client.get(DOCUMENTS_URL, headers=admin_auth_headers)

    assert resp.status_code == 200, f"List documents failed: {resp.text}"
    data = resp.json()

    assert "items" in data, f"Response missing 'items' key: {data}"
    assert len(data["items"]) >= 1, f"Expected at least 1 document in list, got {len(data['items'])}"

    filenames = [doc["filename"] for doc in data["items"]]
    assert "sample_legal_doc.txt" in filenames, f"'sample_legal_doc.txt' not found in document list: {filenames}"


@pytest.mark.e2e
@pytest.mark.slow
async def test_ingest_creates_chunks_in_qdrant(
    ingested_document: dict,
) -> None:
    """After ingestion, the Qdrant collection contains at least one point."""
    from qdrant_client import QdrantClient

    client = QdrantClient(url=QDRANT_URL)
    info = client.get_collection(QDRANT_COLLECTION)

    assert info.points_count > 0, (
        f"Expected points_count > 0 in Qdrant collection '{QDRANT_COLLECTION}', " f"got {info.points_count}"
    )
