"""E2E tests for POST /api/v1/query.

Uses the v1 pipeline (ENABLE_AGENTIC_PIPELINE=false). The LLM is replaced
with FakeLLMClient, so classify/rewrite/synthesize all return deterministic
canned strings. Retrieval is real: the ingested_document fixture has already
put chunks from sample_legal_doc.txt into Qdrant with real bge-small embeddings,
so a query about Acme Corporation regulatory compliance will surface genuine
source documents.
"""

from __future__ import annotations

import re

import pytest
from httpx import AsyncClient

QUERY_URL = "/api/v1/query"
CHATS_URL = "/api/v1/chats"

SAMPLE_QUERY = "Acme Corporation regulatory compliance"

# UUID4 pattern: 8-4-4-4-12 hex groups separated by hyphens
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_valid_uuid4(value: str) -> bool:
    """Return True if *value* is a well-formed UUID v4 string."""
    return bool(_UUID_RE.match(str(value)))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.e2e
async def test_query_returns_response(
    e2e_client: AsyncClient,
    admin_auth_headers: dict[str, str],
    ingested_document: dict,
) -> None:
    """POST /query with a content-relevant question returns 200 and a non-empty response string."""
    resp = await e2e_client.post(
        QUERY_URL,
        json={"query": SAMPLE_QUERY},
        headers=admin_auth_headers,
    )

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "response" in data, "Response body missing 'response' field"
    assert isinstance(data["response"], str), "'response' must be a string"
    assert len(data["response"]) > 0, "'response' must not be empty"


@pytest.mark.e2e
async def test_query_returns_source_documents(
    e2e_client: AsyncClient,
    admin_auth_headers: dict[str, str],
    ingested_document: dict,
) -> None:
    """POST /query about ingested content returns at least one source document."""
    resp = await e2e_client.post(
        QUERY_URL,
        json={"query": SAMPLE_QUERY},
        headers=admin_auth_headers,
    )

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "source_documents" in data, "Response body missing 'source_documents' field"
    assert isinstance(data["source_documents"], list), "'source_documents' must be a list"
    assert (
        len(data["source_documents"]) > 0
    ), "Expected at least one source document for a query matching ingested content"
    # Each source document must have a filename
    for doc in data["source_documents"]:
        assert "filename" in doc, f"Source document missing 'filename': {doc}"
        assert (
            isinstance(doc["filename"], str) and doc["filename"]
        ), f"Source document 'filename' must be a non-empty string: {doc}"


@pytest.mark.e2e
async def test_query_returns_thread_id(
    e2e_client: AsyncClient,
    admin_auth_headers: dict[str, str],
    ingested_document: dict,
) -> None:
    """POST /query response contains a 'thread_id' field that is a valid UUID v4."""
    resp = await e2e_client.post(
        QUERY_URL,
        json={"query": SAMPLE_QUERY},
        headers=admin_auth_headers,
    )

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "thread_id" in data, "Response body missing 'thread_id' field"
    thread_id = data["thread_id"]
    assert isinstance(thread_id, str), "'thread_id' must be a string"
    assert _is_valid_uuid4(thread_id), f"'thread_id' is not a valid UUID v4: {thread_id!r}"


@pytest.mark.e2e
async def test_query_missing_body(
    e2e_client: AsyncClient,
    admin_auth_headers: dict[str, str],
) -> None:
    """POST /query with an empty JSON body returns 422 Unprocessable Entity."""
    resp = await e2e_client.post(
        QUERY_URL,
        json={},
        headers=admin_auth_headers,
    )

    assert (
        resp.status_code == 422
    ), f"Expected 422 for missing required 'query' field, got {resp.status_code}: {resp.text}"


@pytest.mark.e2e
async def test_query_creates_chat_thread(
    e2e_client: AsyncClient,
    admin_auth_headers: dict[str, str],
    ingested_document: dict,
) -> None:
    """After a successful query, GET /chats returns at least one chat thread."""
    # Issue the query to ensure a thread is created
    query_resp = await e2e_client.post(
        QUERY_URL,
        json={"query": SAMPLE_QUERY},
        headers=admin_auth_headers,
    )
    assert query_resp.status_code == 200, f"Query failed before chat thread check: {query_resp.text}"

    # Verify that at least one thread now exists
    chats_resp = await e2e_client.get(CHATS_URL, headers=admin_auth_headers)
    assert chats_resp.status_code == 200, f"GET /chats failed: {chats_resp.status_code}: {chats_resp.text}"
    chats_data = chats_resp.json()
    assert "threads" in chats_data, "GET /chats response missing 'threads' field"
    assert isinstance(chats_data["threads"], list), "'threads' must be a list"
    assert len(chats_data["threads"]) >= 1, "Expected at least one chat thread after issuing a query"
