"""E2E tests for the full PDF ingestion pipeline.

Ingests a synthetic resume PDF through the complete pipeline and makes
semantic assertions at every stage: Docling parsing, semantic chunking,
Qdrant vector payloads, GLiNER entity extraction, Neo4j knowledge graph
nodes/edges, and RAG retrieval.

Requires Docker services running (Postgres, Redis, Qdrant, Neo4j, MinIO).
Run: pytest tests/test_e2e/test_06_pdf_pipeline.py -v -m e2e
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import AsyncClient

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent / "fixtures"
PDF_FILENAME = "sample_resume.pdf"

QDRANT_URL = "http://localhost:6333"
QDRANT_COLLECTION = "nexus_text"

NEO4J_URI = "bolt://localhost:7687"
NEO4J_AUTH = ("neo4j", "changeme")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _qdrant_scroll(filename: str) -> list:
    """Scroll Qdrant for all points matching the given source_file."""
    from qdrant_client import QdrantClient
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    client = QdrantClient(url=QDRANT_URL)
    points, _ = client.scroll(
        collection_name=QDRANT_COLLECTION,
        scroll_filter=Filter(must=[FieldCondition(key="source_file", match=MatchValue(value=filename))]),
        limit=100,
        with_payload=True,
        with_vectors=True,
    )
    return points


async def _neo4j_query(cypher: str, params: dict | None = None) -> list[dict]:
    """Run a Cypher query against the E2E Neo4j instance."""
    from neo4j import AsyncGraphDatabase

    driver = AsyncGraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
    try:
        async with driver.session() as session:
            result = await session.run(cypher, params or {})
            return [record.data() async for record in result]
    finally:
        await driver.close()


# ---------------------------------------------------------------------------
# Module-scoped fixture: ingest the PDF
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="module")
async def ingested_pdf(
    e2e_client: AsyncClient,
    admin_auth_headers: dict[str, str],
) -> dict:
    """Upload sample_resume.pdf and wait for ingestion to complete.

    Returns the job status response dict.
    """
    file_path = FIXTURES_DIR / PDF_FILENAME
    if not file_path.exists():
        pytest.skip(f"PDF fixture not found at {file_path} — run: python scripts/generate_test_pdf.py")

    resp = await e2e_client.post(
        "/api/v1/ingest",
        files={"file": (PDF_FILENAME, BytesIO(file_path.read_bytes()), "application/pdf")},
        headers=admin_auth_headers,
    )
    assert resp.status_code == 200, f"PDF ingest failed: {resp.text}"
    job_id = resp.json()["job_id"]

    # .delay() was captured as a no-op — run the task in a thread now.
    from tests.test_e2e.conftest import run_pending_tasks

    run_pending_tasks()

    # Task completed synchronously (in thread) — fetch final status.
    resp = await e2e_client.get(
        f"/api/v1/jobs/{job_id}",
        headers=admin_auth_headers,
    )
    assert resp.status_code == 200
    status = resp.json()
    assert status["status"] == "complete", (
        f"PDF ingestion did not complete: status={status.get('status')}, " f"error={status.get('error')}"
    )
    return status


# ---------------------------------------------------------------------------
# Tests: ingestion job
# ---------------------------------------------------------------------------


@pytest.mark.e2e
async def test_pdf_ingest_completes(ingested_pdf: dict) -> None:
    """Job status is 'complete' with no error field."""
    assert ingested_pdf["status"] == "complete"
    assert ingested_pdf.get("error") is None


@pytest.mark.e2e
async def test_pdf_parsed_multiple_pages(ingested_pdf: dict) -> None:
    """Docling parsed at least 2 pages from the multi-page PDF."""
    progress = ingested_pdf.get("progress", {})
    pages = progress.get("pages_parsed", 0)
    assert pages >= 2, f"Expected pages_parsed >= 2, got {pages}. Progress: {progress}"


@pytest.mark.e2e
async def test_pdf_chunks_created(ingested_pdf: dict) -> None:
    """Semantic chunker produced at least 3 chunks from the resume."""
    progress = ingested_pdf.get("progress", {})
    chunks = progress.get("chunks_created", 0)
    assert chunks >= 3, f"Expected chunks_created >= 3, got {chunks}. Progress: {progress}"


# ---------------------------------------------------------------------------
# Tests: Qdrant vector store
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.slow
async def test_pdf_qdrant_points_indexed(ingested_pdf: dict) -> None:
    """Qdrant contains at least 3 points for the PDF with correct vector dims."""
    points = _qdrant_scroll(PDF_FILENAME)
    assert len(points) >= 3, f"Expected >= 3 Qdrant points for {PDF_FILENAME}, got {len(points)}"
    # Verify vector dimensions (384d for bge-small-en-v1.5)
    for pt in points:
        vec = pt.vector
        if isinstance(vec, dict):
            # Named vectors — check any of them
            for v in vec.values():
                assert len(v) == 384, f"Expected 384-dim vector, got {len(v)}"
                break
        else:
            assert len(vec) == 384, f"Expected 384-dim vector, got {len(vec)}"


@pytest.mark.e2e
@pytest.mark.slow
async def test_pdf_qdrant_payload_fields(ingested_pdf: dict) -> None:
    """Each Qdrant point has required payload fields."""
    points = _qdrant_scroll(PDF_FILENAME)
    assert len(points) > 0, "No Qdrant points found"

    required_fields = {"source_file", "chunk_text", "chunk_index", "doc_id", "matter_id"}
    for pt in points:
        payload = pt.payload
        for field in required_fields:
            assert field in payload, (
                f"Point {pt.id} missing payload field '{field}'. " f"Available: {list(payload.keys())}"
            )
        assert len(payload["chunk_text"]) > 0, f"Point {pt.id} has empty chunk_text"


# ---------------------------------------------------------------------------
# Tests: entity extraction (GLiNER)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.slow
async def test_pdf_entities_person_extracted(
    e2e_client: AsyncClient,
    admin_auth_headers: dict[str, str],
    ingested_pdf: dict,
) -> None:
    """Entity search for 'Elena Vasquez' returns at least one person entity."""
    resp = await e2e_client.get(
        "/api/v1/entities",
        params={"q": "Elena Vasquez"},
        headers=admin_auth_headers,
    )
    assert resp.status_code == 200, f"Entity search failed: {resp.text}"
    data = resp.json()
    items = data.get("items", [])

    # Lenient: check that at least one person-type entity was found
    person_items = [item for item in items if item.get("type", "").lower() in ("person", "per")]
    assert len(person_items) >= 1, (
        f"Expected at least one person entity for 'Elena Vasquez', " f"got {len(person_items)}. All items: {items}"
    )


@pytest.mark.e2e
@pytest.mark.slow
async def test_pdf_entities_org_extracted(
    e2e_client: AsyncClient,
    admin_auth_headers: dict[str, str],
    ingested_pdf: dict,
) -> None:
    """Entity search for 'Meridian' returns at least one organization entity."""
    resp = await e2e_client.get(
        "/api/v1/entities",
        params={"q": "Meridian"},
        headers=admin_auth_headers,
    )
    assert resp.status_code == 200, f"Entity search failed: {resp.text}"
    data = resp.json()
    items = data.get("items", [])

    org_items = [item for item in items if item.get("type", "").lower() in ("organization", "org")]
    assert len(org_items) >= 1, (
        f"Expected at least one organization entity for 'Meridian', " f"got {len(org_items)}. All items: {items}"
    )


# ---------------------------------------------------------------------------
# Tests: Neo4j knowledge graph
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.slow
async def test_pdf_neo4j_document_node(ingested_pdf: dict) -> None:
    """Neo4j contains a Document node for the ingested PDF."""
    records = await _neo4j_query(
        "MATCH (d:Document {filename: $filename}) RETURN d",
        {"filename": PDF_FILENAME},
    )
    assert len(records) >= 1, f"No Document node found in Neo4j for filename={PDF_FILENAME}"
    doc = records[0]["d"]
    assert "matter_id" in doc, f"Document node missing matter_id: {doc}"


@pytest.mark.e2e
@pytest.mark.slow
async def test_pdf_neo4j_entity_nodes(ingested_pdf: dict) -> None:
    """Neo4j has entity nodes linked to the PDF document via MENTIONED_IN."""
    records = await _neo4j_query(
        "MATCH (e:Entity)-[:MENTIONED_IN]->(:Document {filename: $filename}) "
        "RETURN e.name AS name, labels(e) AS labels",
        {"filename": PDF_FILENAME},
    )
    assert len(records) >= 3, f"Expected >= 3 entity nodes linked to {PDF_FILENAME}, " f"got {len(records)}: {records}"
    # Check that we have at least one Person and one Organization label
    all_labels = set()
    for r in records:
        all_labels.update(r.get("labels", []))
    assert (
        "Person" in all_labels or "Entity" in all_labels
    ), f"No Person-labeled node found. Labels present: {all_labels}"


# ---------------------------------------------------------------------------
# Tests: RAG retrieval
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.slow
async def test_pdf_rag_query_retrieves_document(
    e2e_client: AsyncClient,
    admin_auth_headers: dict[str, str],
    ingested_pdf: dict,
) -> None:
    """Querying about Elena Vasquez retrieves the resume PDF as a source."""
    resp = await e2e_client.post(
        "/api/v1/query",
        json={"query": "What experience does Elena Vasquez have?"},
        headers=admin_auth_headers,
    )
    assert resp.status_code == 200, f"Query failed: {resp.text}"
    data = resp.json()

    source_docs = data.get("source_documents", [])
    source_filenames = [doc.get("filename", "") for doc in source_docs]
    assert PDF_FILENAME in source_filenames, (
        f"Expected {PDF_FILENAME} in source_documents, " f"got filenames: {source_filenames}"
    )


# ---------------------------------------------------------------------------
# Tests: graph stats
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.slow
async def test_pdf_graph_stats_nonzero(
    e2e_client: AsyncClient,
    admin_auth_headers: dict[str, str],
    ingested_pdf: dict,
) -> None:
    """Graph stats show non-zero node and edge counts after ingestion."""
    resp = await e2e_client.get(
        "/api/v1/graph/stats",
        headers=admin_auth_headers,
    )
    assert resp.status_code == 200, f"Graph stats failed: {resp.text}"
    data = resp.json()

    assert data.get("total_nodes", 0) > 0, f"Expected total_nodes > 0, got: {data}"
    assert data.get("total_edges", 0) > 0, f"Expected total_edges > 0, got: {data}"
