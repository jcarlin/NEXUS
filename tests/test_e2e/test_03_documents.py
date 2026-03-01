"""E2E tests for document endpoints.

Covers:
  GET /api/v1/documents
  GET /api/v1/documents/{doc_id}
  GET /api/v1/documents/{doc_id}/preview
  GET /api/v1/documents/{doc_id}/download

Depends on the ingested_document fixture to ensure at least one document
(sample_legal_doc.txt) has been ingested before tests run.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

DOCUMENTS_URL = "/api/v1/documents"


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


async def _get_first_doc_id(
    e2e_client: AsyncClient,
    headers: dict[str, str],
) -> str:
    """List documents and return the ID of the first item."""
    resp = await e2e_client.get(DOCUMENTS_URL, headers=headers)
    assert resp.status_code == 200, f"Failed to list documents: {resp.text}"
    data = resp.json()
    assert data["items"], "No documents found — ingestion may have failed"
    return data["items"][0]["id"]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.e2e
async def test_list_documents_returns_ingested(
    e2e_client: AsyncClient,
    admin_auth_headers: dict[str, str],
    ingested_document: dict,
) -> None:
    """GET /documents returns a non-empty list containing sample_legal_doc.txt."""
    resp = await e2e_client.get(DOCUMENTS_URL, headers=admin_auth_headers)

    assert resp.status_code == 200
    data = resp.json()

    assert "items" in data, "Response missing 'items' key"
    assert "total" in data, "Response missing 'total' key"
    assert "offset" in data, "Response missing 'offset' key"
    assert "limit" in data, "Response missing 'limit' key"

    assert len(data["items"]) > 0, "Expected at least one document in the list"

    filenames = [item["filename"] for item in data["items"]]
    assert "sample_legal_doc.txt" in filenames, f"Expected 'sample_legal_doc.txt' in document list, got: {filenames}"


@pytest.mark.e2e
async def test_list_documents_pagination(
    e2e_client: AsyncClient,
    admin_auth_headers: dict[str, str],
    ingested_document: dict,
) -> None:
    """GET /documents?limit=1 returns exactly one item with total >= 1."""
    resp = await e2e_client.get(
        DOCUMENTS_URL,
        params={"limit": 1},
        headers=admin_auth_headers,
    )

    assert resp.status_code == 200
    data = resp.json()

    assert len(data["items"]) == 1, f"Expected exactly 1 item with limit=1, got {len(data['items'])}"
    assert data["total"] >= 1, f"Expected total >= 1, got {data['total']}"
    assert data["limit"] == 1, f"Expected limit=1 in response, got {data['limit']}"


@pytest.mark.e2e
async def test_get_document_detail(
    e2e_client: AsyncClient,
    admin_auth_headers: dict[str, str],
    ingested_document: dict,
) -> None:
    """GET /documents/{id} returns full document detail with chunk_count > 0."""
    doc_id = await _get_first_doc_id(e2e_client, admin_auth_headers)

    resp = await e2e_client.get(
        f"{DOCUMENTS_URL}/{doc_id}",
        headers=admin_auth_headers,
    )

    assert resp.status_code == 200
    data = resp.json()

    assert data["id"] == doc_id, f"Returned doc ID {data.get('id')} does not match requested {doc_id}"
    assert "filename" in data, "Response missing 'filename' key"
    assert "chunk_count" in data, "Response missing 'chunk_count' key"
    assert data["chunk_count"] > 0, f"Expected chunk_count > 0 after ingestion, got {data['chunk_count']}"
    # Full detail fields
    assert (
        "metadata_" in data or "job_id" in data
    ), "Expected full detail fields (metadata_ or job_id) in document detail response"


@pytest.mark.e2e
async def test_document_preview_returns_url(
    e2e_client: AsyncClient,
    admin_auth_headers: dict[str, str],
    ingested_document: dict,
) -> None:
    """GET /documents/{id}/preview?page=1 returns 200 with an image_url string."""
    doc_id = await _get_first_doc_id(e2e_client, admin_auth_headers)

    resp = await e2e_client.get(
        f"{DOCUMENTS_URL}/{doc_id}/preview",
        params={"page": 1},
        headers=admin_auth_headers,
    )

    assert resp.status_code == 200
    data = resp.json()

    assert "image_url" in data, f"Response missing 'image_url' key: {data}"
    assert isinstance(data["image_url"], str), f"Expected 'image_url' to be a string, got {type(data['image_url'])}"
    assert data["image_url"].startswith("http"), f"Expected 'image_url' to start with 'http', got: {data['image_url']}"
    assert data["doc_id"] == doc_id, f"Response doc_id {data.get('doc_id')} does not match requested {doc_id}"
    assert data["page"] == 1, f"Expected page=1 in response, got {data.get('page')}"


@pytest.mark.e2e
async def test_document_download_returns_url(
    e2e_client: AsyncClient,
    admin_auth_headers: dict[str, str],
    ingested_document: dict,
) -> None:
    """GET /documents/{id}/download returns 200 with a download_url string."""
    doc_id = await _get_first_doc_id(e2e_client, admin_auth_headers)

    resp = await e2e_client.get(
        f"{DOCUMENTS_URL}/{doc_id}/download",
        headers=admin_auth_headers,
    )

    assert resp.status_code == 200
    data = resp.json()

    assert "download_url" in data, f"Response missing 'download_url' key: {data}"
    assert isinstance(
        data["download_url"], str
    ), f"Expected 'download_url' to be a string, got {type(data['download_url'])}"
    assert data["download_url"].startswith(
        "http"
    ), f"Expected 'download_url' to start with 'http', got: {data['download_url']}"
    assert "doc_id" in data, "Response missing 'doc_id' key"
    assert "filename" in data, "Response missing 'filename' key"


@pytest.mark.e2e
async def test_get_nonexistent_document(
    e2e_client: AsyncClient,
    admin_auth_headers: dict[str, str],
) -> None:
    """GET /documents/{random_uuid} returns 404 for a document that does not exist."""
    random_id = str(uuid.uuid4())

    resp = await e2e_client.get(
        f"{DOCUMENTS_URL}/{random_id}",
        headers=admin_auth_headers,
    )

    assert resp.status_code == 404, f"Expected 404 for nonexistent document, got {resp.status_code}: {resp.text}"
