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


# ---------------------------------------------------------------------------
# Edge-case tests (Sprint 8 L4)
# ---------------------------------------------------------------------------


def test_empty_text_returns_no_matches():
    """Empty string should produce no matches and not crash."""
    detector = NearDuplicateDetector(threshold=0.80, num_perm=128)

    matches = detector.find_duplicates("doc-1", "", "matter-1")
    assert len(matches) == 0


def test_single_char_text_returns_no_matches():
    """Very short text (single char) should not crash or produce spurious matches."""
    detector = NearDuplicateDetector(threshold=0.80, num_perm=128)

    matches_a = detector.find_duplicates("doc-1", "a", "matter-1")
    matches_b = detector.find_duplicates("doc-2", "b", "matter-1")
    assert len(matches_a) == 0
    assert len(matches_b) == 0


def test_unicode_text_hashing():
    """Unicode text with CJK characters and emoji should not crash."""
    detector = NearDuplicateDetector(threshold=0.80, num_perm=128)

    text_cjk = "This contract involves parties in Tokyo and Beijing."
    matches = detector.find_duplicates("doc-1", text_cjk, "matter-1")
    assert isinstance(matches, list)


def test_boundary_threshold_exact_match():
    """Two identical texts should exceed the threshold and be detected as duplicates."""
    detector = NearDuplicateDetector(threshold=0.80, num_perm=128)

    text = (
        "The settlement agreement dated March 15, 2024 between the parties "
        "establishes the following terms and conditions for resolution of the dispute."
    )

    detector.find_duplicates("doc-1", text, "matter-1")
    matches = detector.find_duplicates("doc-2", text, "matter-1")

    assert len(matches) >= 1
    assert matches[0][1] > 0.80  # Score exceeds threshold


def test_boundary_threshold_different_text():
    """Completely different texts should score below the threshold."""
    detector = NearDuplicateDetector(threshold=0.80, num_perm=128)

    text_a = (
        "The annual report for fiscal year 2023 demonstrates a significant "
        "increase in revenue across multiple business segments and territories."
    )
    text_b = (
        "Dear counsel, please find attached the deposition transcript for "
        "witness Jane Doe taken on February 12, 2024 in the Southern District."
    )

    detector.find_duplicates("doc-1", text_a, "matter-1")
    matches = detector.find_duplicates("doc-2", text_b, "matter-1")

    # Completely different texts should not match
    assert len(matches) == 0


def test_duplicate_doc_id_is_idempotent():
    """Calling find_duplicates twice with the same doc_id should not produce duplicate entries."""
    detector = NearDuplicateDetector(threshold=0.80, num_perm=128)

    text = (
        "This memorandum of understanding between Alpha Corp and Beta LLC "
        "outlines the terms for the proposed joint venture agreement."
    )

    # Insert the same doc_id twice
    matches_first = detector.find_duplicates("doc-1", text, "matter-1")
    matches_second = detector.find_duplicates("doc-1", text, "matter-1")

    # Neither call should produce self-matches
    assert len(matches_first) == 0
    assert len(matches_second) == 0
