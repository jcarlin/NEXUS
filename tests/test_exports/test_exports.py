"""Tests for the export module.

Tests cover EDRM XML generation with Bates numbers, privilege log generation,
production set lifecycle, and result set export ZIP structure.
"""

from __future__ import annotations

import csv
import io
import json
import zipfile
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.edrm.loadfile_parser import LoadFileParser
from app.edrm.schemas import LoadFileRecord

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_production_set_row(ps_id=None, **overrides) -> dict:
    """Return a dict mimicking a raw DB row from the production_sets table."""
    base = {
        "id": ps_id or uuid4(),
        "matter_id": uuid4(),
        "name": "Production Set 1",
        "description": "Initial production",
        "bates_prefix": "NEXUS",
        "bates_start": 1,
        "bates_padding": 6,
        "next_bates": 1,
        "status": "draft",
        "created_by": uuid4(),
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
        "document_count": 0,
    }
    base.update(overrides)
    return base


def _fake_export_job_row(job_id=None, **overrides) -> dict:
    """Return a dict mimicking a raw DB row from the export_jobs table."""
    base = {
        "id": job_id or uuid4(),
        "matter_id": uuid4(),
        "export_type": "court_ready",
        "export_format": "zip",
        "status": "pending",
        "parameters": {},
        "output_path": None,
        "file_size_bytes": None,
        "error": None,
        "created_by": uuid4(),
        "created_at": datetime.now(UTC),
        "completed_at": None,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Test 1: EDRM XML output includes BEGBATES/ENDBATES Tag elements
# ---------------------------------------------------------------------------


def test_edrm_export_with_bates() -> None:
    """EDRM XML output should include BEGBATES and ENDBATES as Tag elements."""
    records = [
        LoadFileRecord(
            doc_id="DOC001",
            fields={
                "Filename": "contract.pdf",
                "BEGBATES": "NEXUS-000001",
                "ENDBATES": "NEXUS-000010",
            },
        ),
        LoadFileRecord(
            doc_id="DOC002",
            fields={
                "Filename": "email.msg",
                "BEGBATES": "NEXUS-000011",
                "ENDBATES": "NEXUS-000015",
            },
        ),
    ]

    xml_output = LoadFileParser.export_edrm_xml(records)

    assert "BEGBATES" in xml_output
    assert "ENDBATES" in xml_output
    assert "NEXUS-000001" in xml_output
    assert "NEXUS-000010" in xml_output
    assert "NEXUS-000011" in xml_output
    assert "NEXUS-000015" in xml_output

    # Verify it's valid XML with correct structure
    import xml.etree.ElementTree as ET

    root = ET.fromstring(xml_output)
    doc_elements = root.findall(".//Document")
    assert len(doc_elements) == 2

    # Verify BEGBATES and ENDBATES appear as Tag elements
    first_doc_tags = doc_elements[0].findall("Tag")
    tag_names = {t.get("TagName") for t in first_doc_tags}
    assert "BEGBATES" in tag_names
    assert "ENDBATES" in tag_names


# ---------------------------------------------------------------------------
# Test 2: Privilege log generation has correct columns and basis mapping
# ---------------------------------------------------------------------------


def test_privilege_log_generation() -> None:
    """Privilege log CSV should have expected columns and map privilege_status."""
    from app.exports.generators import generate_privilege_log

    # Create a mock engine that returns privileged documents
    mock_conn = MagicMock()
    mock_result = MagicMock()
    mock_rows = [
        MagicMock(
            _mapping={
                "bates_begin": "NEXUS-000001",
                "bates_end": "NEXUS-000010",
                "filename": "contract.pdf",
                "document_type": "correspondence",
                "document_date": datetime(2025, 6, 15, tzinfo=UTC),
                "privilege_status": "privileged",
                "privilege_reviewed_by": uuid4(),
                "privilege_reviewed_at": datetime(2025, 7, 1, tzinfo=UTC),
                "metadata_": {},
            }
        ),
        MagicMock(
            _mapping={
                "bates_begin": "NEXUS-000011",
                "bates_end": "NEXUS-000015",
                "filename": "memo.docx",
                "document_type": "legal_filing",
                "document_date": None,  # PDF with no real date — should render as ""
                "privilege_status": "work_product",
                "privilege_reviewed_by": uuid4(),
                "privilege_reviewed_at": datetime(2025, 7, 2, tzinfo=UTC),
                "metadata_": {},
            }
        ),
    ]
    mock_result.all.return_value = mock_rows
    mock_conn.execute.return_value = mock_result
    mock_engine = MagicMock()
    mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
    mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

    data = generate_privilege_log(mock_engine, str(uuid4()), fmt="csv")

    # Parse CSV
    reader = csv.reader(io.StringIO(data.decode("utf-8")))
    rows = list(reader)

    # Header row
    header = rows[0]
    assert "Bates Begin" in header
    assert "Bates End" in header
    assert "Privilege Status" in header
    assert "Privilege Basis" in header
    assert "Date" in header

    # Data rows
    assert len(rows) == 3  # header + 2 data rows

    # Check basis mapping
    assert rows[1][header.index("Privilege Basis")] == "Attorney-Client Privilege"
    assert rows[2][header.index("Privilege Basis")] == "Work Product Doctrine"

    # Date column must come from document_date (real communication date),
    # not the ingestion timestamp. NULL document_date renders as blank
    # rather than fabricating a date from created_at.
    date_col = header.index("Date")
    assert rows[1][date_col] == "2025-06-15T00:00:00+00:00"
    assert rows[2][date_col] == ""


# ---------------------------------------------------------------------------
# Test 3: Production set lifecycle (create → add docs → assign Bates)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_production_set_lifecycle(client: AsyncClient) -> None:
    """Production set: create → add docs → assign Bates → finalized."""
    ps_id = uuid4()
    doc_id = uuid4()

    # Step 1: Create production set
    ps_row = _fake_production_set_row(ps_id=ps_id)
    with patch(
        "app.exports.service.ExportService.create_production_set",
        new_callable=AsyncMock,
        return_value=ps_row,
    ):
        response = await client.post(
            "/api/v1/exports/production-sets",
            json={"name": "Production Set 1"},
        )
    assert response.status_code == 201
    assert response.json()["status"] == "draft"

    # Step 2: Add documents
    psd_row = {
        "id": uuid4(),
        "production_set_id": ps_id,
        "document_id": doc_id,
        "bates_begin": None,
        "bates_end": None,
        "added_at": datetime.now(UTC),
    }
    with patch(
        "app.exports.service.ExportService.add_documents_to_production_set",
        new_callable=AsyncMock,
        return_value=[psd_row],
    ):
        response = await client.post(
            f"/api/v1/exports/production-sets/{ps_id}/documents",
            json={"document_ids": [str(doc_id)]},
        )
    assert response.status_code == 200
    assert len(response.json()) == 1

    # Step 3: Assign Bates numbers
    finalized_row = _fake_production_set_row(
        ps_id=ps_id,
        status="finalized",
        next_bates=13,
        document_count=1,
    )
    with patch(
        "app.exports.service.ExportService.assign_bates_numbers",
        new_callable=AsyncMock,
        return_value=finalized_row,
    ):
        response = await client.post(
            f"/api/v1/exports/production-sets/{ps_id}/assign-bates",
        )
    assert response.status_code == 200
    assert response.json()["status"] == "finalized"


# ---------------------------------------------------------------------------
# Test 4: Result set export ZIP structure
# ---------------------------------------------------------------------------


def test_result_set_export_zip_structure() -> None:
    """Court-ready export ZIP should contain citation_index.csv, privilege_log.csv, manifest.json."""
    from app.exports.generators import generate_court_ready

    # Create a mock engine
    mock_conn = MagicMock()
    mock_result = MagicMock()
    doc_id = uuid4()
    mock_rows = [
        MagicMock(
            _mapping={
                "id": doc_id,
                "filename": "report.pdf",
                "document_type": "deposition",
                "page_count": 12,
                "minio_path": "raw/abc/report.pdf",
                "file_size_bytes": 204800,
                "bates_begin": "NEXUS-000001",
                "bates_end": "NEXUS-000012",
                "privilege_status": None,
                "privilege_reviewed_by": None,
                "privilege_reviewed_at": None,
                "created_at": datetime(2025, 6, 15, tzinfo=UTC),
                "metadata_": {},
            }
        ),
    ]
    mock_result.all.return_value = mock_rows
    mock_conn.execute.return_value = mock_result
    mock_engine = MagicMock()
    mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
    mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

    data = generate_court_ready(mock_engine, str(uuid4()))

    # Verify it's a valid ZIP
    zf = zipfile.ZipFile(io.BytesIO(data))
    names = zf.namelist()

    assert "citation_index.csv" in names
    assert "privilege_log.csv" in names
    assert "manifest.json" in names

    # Verify citation_index.csv content
    csv_content = zf.read("citation_index.csv").decode("utf-8")
    reader = csv.reader(io.StringIO(csv_content))
    rows = list(reader)
    assert rows[0] == ["doc_id", "filename", "bates_begin", "bates_end", "page_count"]
    assert len(rows) == 2  # header + 1 doc
    assert rows[1][1] == "report.pdf"
    assert rows[1][2] == "NEXUS-000001"

    # Verify manifest.json
    manifest = json.loads(zf.read("manifest.json"))
    assert manifest["export_type"] == "court_ready"
    assert manifest["document_count"] == 1
    assert len(manifest["documents"]) == 1

    zf.close()
