"""Tests for the POST /ingest/import/dry-run endpoint."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

# ---------------------------------------------------------------------------
# Basic estimation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dry_run_returns_estimates(client: AsyncClient) -> None:
    """POST /ingest/import/dry-run should return estimated import metrics."""
    resp = await client.post(
        "/api/v1/ingest/import/dry-run",
        json={
            "source_type": "upload",
            "file_count": 100,
            "total_size_bytes": 500_000_000,
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["estimated_documents"] == 100
    assert data["estimated_chunks"] > 0
    assert data["estimated_duration_minutes"] > 0
    assert data["estimated_storage_mb"] > 0
    assert isinstance(data["warnings"], list)


@pytest.mark.asyncio
async def test_dry_run_s3_source_type(client: AsyncClient) -> None:
    """POST /ingest/import/dry-run accepts 's3' source_type."""
    resp = await client.post(
        "/api/v1/ingest/import/dry-run",
        json={
            "source_type": "s3",
            "file_count": 10,
            "total_size_bytes": 1_000_000,
            "s3_prefix": "data/case-001/",
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["estimated_documents"] == 10


@pytest.mark.asyncio
async def test_dry_run_load_file_source_type(client: AsyncClient) -> None:
    """POST /ingest/import/dry-run accepts 'load_file' source_type."""
    resp = await client.post(
        "/api/v1/ingest/import/dry-run",
        json={
            "source_type": "load_file",
            "file_count": 50,
            "total_size_bytes": 200_000_000,
            "load_file_path": "/data/import/manifest.jsonl",
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["estimated_documents"] == 50


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dry_run_rejects_invalid_source_type(client: AsyncClient) -> None:
    """POST /ingest/import/dry-run with invalid source_type returns 422."""
    resp = await client.post(
        "/api/v1/ingest/import/dry-run",
        json={
            "source_type": "ftp",
            "file_count": 10,
        },
    )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_dry_run_rejects_missing_source_type(client: AsyncClient) -> None:
    """POST /ingest/import/dry-run without source_type returns 422."""
    resp = await client.post(
        "/api/v1/ingest/import/dry-run",
        json={"file_count": 10},
    )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_dry_run_rejects_negative_file_count(client: AsyncClient) -> None:
    """POST /ingest/import/dry-run with file_count=0 returns 422 (ge=1)."""
    resp = await client.post(
        "/api/v1/ingest/import/dry-run",
        json={
            "source_type": "upload",
            "file_count": 0,
        },
    )

    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Warnings
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dry_run_warns_large_import(client: AsyncClient) -> None:
    """Large file_count should trigger a batching warning."""
    resp = await client.post(
        "/api/v1/ingest/import/dry-run",
        json={
            "source_type": "upload",
            "file_count": 2000,
            "total_size_bytes": 1_000_000,
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert any("batching" in w.lower() for w in data["warnings"])


@pytest.mark.asyncio
async def test_dry_run_warns_large_size(client: AsyncClient) -> None:
    """Import exceeding 10 GB should trigger a storage warning."""
    resp = await client.post(
        "/api/v1/ingest/import/dry-run",
        json={
            "source_type": "upload",
            "file_count": 100,
            "total_size_bytes": 15 * 1024**3,  # 15 GB
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert any("10 gb" in w.lower() for w in data["warnings"])


@pytest.mark.asyncio
async def test_dry_run_no_warnings_small_import(client: AsyncClient) -> None:
    """Small imports should have no warnings."""
    resp = await client.post(
        "/api/v1/ingest/import/dry-run",
        json={
            "source_type": "upload",
            "file_count": 10,
            "total_size_bytes": 5_000_000,
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["warnings"] == []
