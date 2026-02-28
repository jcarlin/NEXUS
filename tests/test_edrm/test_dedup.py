"""Tests for near-duplicate detection using MinHash + LSH."""

from __future__ import annotations

from app.ingestion.dedup import NearDuplicateDetector


# ---------------------------------------------------------------------------
# Exact duplicate detection (1)
# ---------------------------------------------------------------------------

def test_exact_duplicate_detected():
    """Two identical documents should be detected as duplicates."""
    detector = NearDuplicateDetector(threshold=0.80, num_perm=128)

    text_a = "This is a contract between Party A and Party B for the sale of goods."
    text_b = "This is a contract between Party A and Party B for the sale of goods."

    # Insert first document
    matches_a = detector.find_duplicates("doc-1", text_a, "matter-1")
    assert len(matches_a) == 0  # No matches yet

    # Insert identical document
    matches_b = detector.find_duplicates("doc-2", text_b, "matter-1")
    assert len(matches_b) >= 1
    assert any(m[0] == "doc-1" for m in matches_b)
    # Score should be very high (near 1.0) for identical text
    assert matches_b[0][1] > 0.95


# ---------------------------------------------------------------------------
# Near-duplicate above threshold (1)
# ---------------------------------------------------------------------------

def test_near_duplicate_above_threshold():
    """Two similar documents above the threshold should be detected."""
    detector = NearDuplicateDetector(threshold=0.50, num_perm=128)

    text_a = (
        "This agreement is made between Alpha Corp and Beta LLC. "
        "The parties agree to the following terms and conditions "
        "regarding the delivery of software services. The contract "
        "shall be effective from January 1, 2024 and shall remain "
        "in effect until December 31, 2024."
    )
    # Similar but with some changes
    text_b = (
        "This agreement is made between Alpha Corp and Beta LLC. "
        "The parties agree to the following terms and conditions "
        "regarding the delivery of consulting services. The contract "
        "shall be effective from March 1, 2024 and shall remain "
        "in effect until February 28, 2025."
    )

    detector.find_duplicates("doc-1", text_a, "matter-1")
    matches = detector.find_duplicates("doc-2", text_b, "matter-1")

    assert len(matches) >= 1
    assert any(m[0] == "doc-1" for m in matches)


# ---------------------------------------------------------------------------
# Dissimilar documents not matched (1)
# ---------------------------------------------------------------------------

def test_dissimilar_documents_not_matched():
    """Two completely different documents should not be matched."""
    detector = NearDuplicateDetector(threshold=0.80, num_perm=128)

    text_a = (
        "The quarterly financial report shows revenue growth of 15% "
        "across all business segments. Operating expenses decreased "
        "by 3% compared to the previous quarter."
    )
    text_b = (
        "Dear Mr. Johnson, I am writing to schedule a deposition "
        "for the matter of Smith v. Jones. Please advise on your "
        "availability for the week of March 15."
    )

    detector.find_duplicates("doc-1", text_a, "matter-1")
    matches = detector.find_duplicates("doc-2", text_b, "matter-1")

    # Should not match — completely different content
    assert len(matches) == 0
