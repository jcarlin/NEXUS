"""Tests for the redaction module (M14b).

These tests cover PII detection, the pikepdf redaction engine,
redaction log immutability, router endpoints, feature flag guard,
and a full integration flow.
"""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pikepdf
import pytest
from httpx import AsyncClient

from app.redaction.pii_detector import detect_pii
from app.redaction.schemas import PIICategory, RedactionSpec, RedactionType

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_test_pdf(text: str, path: Path) -> None:
    """Create a minimal single-page PDF containing *text* via a Tj operator."""
    pdf = pikepdf.Pdf.new()
    content = f"BT /F1 12 Tf 100 700 Td ({text}) Tj ET".encode()
    page_dict = pikepdf.Dictionary(
        Type=pikepdf.Name.Page,
        MediaBox=[0, 0, 612, 792],
        Contents=pdf.make_stream(content),
        Resources=pikepdf.Dictionary(
            Font=pikepdf.Dictionary(
                F1=pikepdf.Dictionary(
                    Type=pikepdf.Name.Font,
                    Subtype=pikepdf.Name.Type1,
                    BaseFont=pikepdf.Name.Helvetica,
                )
            )
        ),
    )
    pdf.pages.append(pikepdf.Page(page_dict))
    pdf.save(path)
    pdf.close()


def _fake_redaction_log_row(**overrides) -> dict:
    """Return a dict mimicking a raw DB row from the redactions table."""
    base = {
        "id": uuid4(),
        "document_id": uuid4(),
        "matter_id": uuid4(),
        "user_id": uuid4(),
        "redaction_type": "pii",
        "pii_category": "ssn",
        "page_number": 1,
        "span_start": 5,
        "span_end": 16,
        "reason": "PII: SSN detected",
        "original_text_hash": "a" * 64,
        "created_at": datetime.now(UTC),
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# 1. PII detection — SSN pattern
# ---------------------------------------------------------------------------


def test_pii_detection_ssn() -> None:
    """detect_pii should find SSN patterns with correct offsets."""
    text = "My SSN is 123-45-6789 and that is private."
    detections = detect_pii(text)

    ssn_detections = [d for d in detections if d.category == PIICategory.SSN]
    assert len(ssn_detections) == 1

    ssn = ssn_detections[0]
    assert ssn.text == "123-45-6789"
    assert ssn.confidence == 1.0
    assert ssn.start == 10
    assert ssn.end == 21
    assert text[ssn.start : ssn.end] == "123-45-6789"


# ---------------------------------------------------------------------------
# 2. PII detection — phone, email, DOB
# ---------------------------------------------------------------------------


def test_pii_detection_multiple_types() -> None:
    """detect_pii should find phone, email, and DOB patterns."""
    text = "Contact John at (555) 123-4567 or john@example.com. " "DOB: 01/15/1990. Diagnosis noted in file."
    detections = detect_pii(text)

    categories = {d.category for d in detections}
    assert PIICategory.PHONE in categories
    assert PIICategory.EMAIL in categories
    assert PIICategory.DOB in categories
    assert PIICategory.MEDICAL in categories

    # Verify email detection
    email_dets = [d for d in detections if d.category == PIICategory.EMAIL]
    assert len(email_dets) == 1
    assert email_dets[0].text == "john@example.com"

    # Verify DOB detection
    dob_dets = [d for d in detections if d.category == PIICategory.DOB]
    assert len(dob_dets) == 1
    assert dob_dets[0].text == "01/15/1990"

    # Verify medical keyword detection (lower confidence)
    medical_dets = [d for d in detections if d.category == PIICategory.MEDICAL]
    assert len(medical_dets) >= 1
    assert all(d.confidence == 0.9 for d in medical_dets)


# ---------------------------------------------------------------------------
# 3. Privilege redaction suggestion
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_privilege_redaction_suggestion() -> None:
    """suggest_privilege_redactions returns suggestion for privileged docs."""
    from app.redaction.service import RedactionService

    doc_id = uuid4()
    matter_id = uuid4()

    # Mock DB returning a privileged document
    mock_result = MagicMock()
    mock_row = MagicMock()
    mock_row._mapping = {"id": doc_id, "privilege_status": "privileged"}
    mock_result.first.return_value = mock_row

    mock_db = AsyncMock()
    mock_db.execute.return_value = mock_result

    suggestions = await RedactionService.suggest_privilege_redactions(
        db=mock_db,
        matter_id=matter_id,
        document_id=doc_id,
    )

    assert len(suggestions) == 1
    assert suggestions[0].text == "[Full document — privilege-protected]"
    assert suggestions[0].confidence == 1.0


# ---------------------------------------------------------------------------
# 4. Redaction engine — text removal
# ---------------------------------------------------------------------------


def test_redaction_engine_text_removal() -> None:
    """redact_pdf should physically remove text from the PDF content stream."""
    from app.redaction.engine import redact_pdf, verify_redaction

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        input_path = tmp / "input.pdf"
        output_path = tmp / "output.pdf"

        # Create PDF with "SSN: 123-45-6789"
        _create_test_pdf("SSN: 123-45-6789", input_path)

        # Redact "123-45-6789" (positions 5 to 16 in the text string)
        specs = [
            RedactionSpec(
                page_number=1,
                start=5,
                end=16,
                reason="PII: SSN",
                redaction_type=RedactionType.PII,
                pii_category=PIICategory.SSN,
            )
        ]

        count = redact_pdf(input_path, output_path, specs)
        assert count == 1

        # Verify the SSN is gone from the content stream
        verified = verify_redaction(output_path, ["123-45-6789"])
        assert verified is True, "Redacted text still found in PDF content stream"


# ---------------------------------------------------------------------------
# 5. Redaction log immutability
# ---------------------------------------------------------------------------


def test_redaction_log_entry_has_no_updated_at() -> None:
    """RedactionLogEntry schema should have created_at but no updated_at."""
    from app.redaction.schemas import RedactionLogEntry

    # Verify the model fields
    field_names = set(RedactionLogEntry.model_fields.keys())
    assert "created_at" in field_names
    assert "updated_at" not in field_names, "Redaction log entries must be immutable (no updated_at)"

    # Verify a log entry can be constructed with created_at
    entry = RedactionLogEntry(
        id=uuid4(),
        document_id=uuid4(),
        matter_id=uuid4(),
        user_id=uuid4(),
        redaction_type="pii",
        pii_category="ssn",
        page_number=1,
        reason="PII: SSN detected",
        original_text_hash="a" * 64,
        created_at=datetime.now(UTC),
    )
    assert entry.created_at is not None


# ---------------------------------------------------------------------------
# 6. Router — POST /documents/{id}/redact
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_redact_endpoint(client: AsyncClient) -> None:
    """POST /documents/{id}/redact should return 200 with redaction summary."""
    doc_id = uuid4()
    matter_id = uuid4()

    mock_result = {
        "document_id": doc_id,
        "matter_id": matter_id,
        "redaction_count": 2,
        "redacted_pdf_path": f"redacted/{matter_id}/{doc_id}.pdf",
    }

    mock_settings = MagicMock()
    mock_settings.enable_redaction = True

    with (
        patch("app.config.Settings", return_value=mock_settings),
        patch(
            "app.redaction.service.RedactionService.apply_redactions",
            new_callable=AsyncMock,
            return_value=mock_result,
        ),
    ):
        response = await client.post(
            f"/api/v1/documents/{doc_id}/redact",
            json={
                "redactions": [
                    {
                        "start": 5,
                        "end": 16,
                        "reason": "PII: SSN",
                        "redaction_type": "pii",
                        "pii_category": "ssn",
                    },
                    {
                        "start": 20,
                        "end": 35,
                        "reason": "PII: phone",
                        "redaction_type": "pii",
                        "pii_category": "phone",
                    },
                ],
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["document_id"] == str(doc_id)
    assert body["redaction_count"] == 2
    assert "redacted_pdf_path" in body


# ---------------------------------------------------------------------------
# 7. Router — GET /documents/{id}/redaction-log
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_redaction_log_endpoint(client: AsyncClient) -> None:
    """GET /documents/{id}/redaction-log should return paginated log."""
    doc_id = uuid4()
    log_entry = _fake_redaction_log_row(document_id=doc_id)

    mock_settings = MagicMock()
    mock_settings.enable_redaction = True

    with (
        patch("app.config.Settings", return_value=mock_settings),
        patch(
            "app.redaction.service.RedactionService.get_redaction_log",
            new_callable=AsyncMock,
            return_value=([log_entry], 1),
        ),
    ):
        response = await client.get(
            f"/api/v1/documents/{doc_id}/redaction-log",
        )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert "offset" in body
    assert "limit" in body
    assert body["items"][0]["redaction_type"] == "pii"


# ---------------------------------------------------------------------------
# 8. Integration — full flow: detect PII → redact PDF → verify
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_redact_endpoint_returns_501_when_disabled(client: AsyncClient) -> None:
    """All redaction endpoints return 501 when ENABLE_REDACTION=false."""
    doc_id = uuid4()

    mock_settings = MagicMock()
    mock_settings.enable_redaction = False

    with patch("app.config.Settings", return_value=mock_settings):
        # POST /documents/{id}/redact
        r1 = await client.post(
            f"/api/v1/documents/{doc_id}/redact",
            json={"redactions": [{"start": 0, "end": 10, "reason": "test"}]},
        )
        assert r1.status_code == 501
        assert "not enabled" in r1.json()["detail"].lower()

        # GET /documents/{id}/redaction-log
        r2 = await client.get(f"/api/v1/documents/{doc_id}/redaction-log")
        assert r2.status_code == 501

        # GET /documents/{id}/pii-detections
        r3 = await client.get(f"/api/v1/documents/{doc_id}/pii-detections")
        assert r3.status_code == 501


def test_integration_pii_detect_redact_verify() -> None:
    """Full flow: detect PII in text, build redaction specs, apply to PDF, verify."""
    from app.redaction.engine import redact_pdf, verify_redaction

    # Step 1: detect PII in text
    sample_text = "SSN: 123-45-6789"
    detections = detect_pii(sample_text)
    ssn_det = [d for d in detections if d.category == PIICategory.SSN]
    assert len(ssn_det) == 1

    # Step 2: build redaction specs from detections
    det = ssn_det[0]
    specs = [
        RedactionSpec(
            page_number=1,
            start=det.start,
            end=det.end,
            reason=f"PII: {det.category.value}",
            redaction_type=RedactionType.PII,
            pii_category=det.category,
        )
    ]

    # Step 3: create a PDF with the same text and apply redactions
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        input_path = tmp / "input.pdf"
        output_path = tmp / "output.pdf"

        _create_test_pdf(sample_text, input_path)

        # Verify text IS present before redaction
        before = verify_redaction(input_path, ["123-45-6789"])
        assert before is False, "SSN should be present in original PDF"

        # Apply redactions
        count = redact_pdf(input_path, output_path, specs)
        assert count >= 1

        # Step 4: verify text is GONE after redaction
        after = verify_redaction(output_path, ["123-45-6789"])
        assert after is True, "SSN must be physically removed, not just visually masked"
