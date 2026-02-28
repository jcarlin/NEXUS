"""Tests for version detection via filename pattern extraction."""

from __future__ import annotations

from app.ingestion.dedup import VersionDetector


def test_filename_version_extraction():
    """Version indicators should be extracted from filenames."""
    # Standard version patterns
    label, is_final = VersionDetector.extract_version_info("contract_v1.pdf")
    assert label == "v1"
    assert is_final is False

    label, is_final = VersionDetector.extract_version_info("contract_v2.pdf")
    assert label == "v2"
    assert is_final is False

    label, is_final = VersionDetector.extract_version_info("contract_draft.pdf")
    assert label == "draft"
    assert is_final is False

    label, is_final = VersionDetector.extract_version_info("contract_final.pdf")
    assert label == "final"
    assert is_final is True

    label, is_final = VersionDetector.extract_version_info("agreement-rev3.docx")
    assert label is not None
    assert "rev" in label.lower()

    # No version indicator
    label, is_final = VersionDetector.extract_version_info("monthly_report.pdf")
    assert label is None
    assert is_final is False
