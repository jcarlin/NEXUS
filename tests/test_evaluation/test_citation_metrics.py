"""Tests for citation provenance metrics."""

from __future__ import annotations

from evaluation.metrics.citation import (
    ExtractedCitation,
    citation_accuracy,
    extract_citations,
    hallucination_rate,
    post_rationalization_rate,
)


class TestExtractCitations:
    def test_extract_citations_regex(self) -> None:
        """Parses [Source: file.pdf, page 3] correctly."""
        text = (
            "The contract was signed in January "
            "[Source: msa-2024.pdf, page 12]. "
            "The amendment was filed later "
            "[Source: amendment-001.pdf, Page 5]. "
            "No citation here. "
            "[Source: complaint.pdf, page 1]"
        )
        citations = extract_citations(text)

        assert len(citations) == 3
        assert citations[0].filename == "msa-2024.pdf"
        assert citations[0].page == 12
        assert citations[1].filename == "amendment-001.pdf"
        assert citations[1].page == 5
        assert citations[2].filename == "complaint.pdf"
        assert citations[2].page == 1

        # No citations in text
        assert extract_citations("Just some plain text.") == []

        # Malformed citation
        assert extract_citations("[Source: missing-page.pdf]") == []


class TestCitationAccuracy:
    def test_citation_accuracy(self) -> None:
        """Known citations vs expected ranges produce correct score."""
        extracted = [
            ExtractedCitation(filename="complaint.pdf", page=3),
            ExtractedCitation(filename="msa-2024.pdf", page=12),
            ExtractedCitation(filename="unknown.pdf", page=1),
        ]

        expected = [
            {"document_id": "complaint.pdf", "page_start": 1, "page_end": 5},
            {"document_id": "msa-2024.pdf", "page_start": 10, "page_end": 15},
        ]

        # 2 of 3 match → accuracy ≈ 0.667
        accuracy = citation_accuracy(extracted, expected)
        assert abs(accuracy - 2 / 3) < 1e-9

        # All match
        extracted_all = [
            ExtractedCitation(filename="complaint.pdf", page=3),
            ExtractedCitation(filename="msa-2024.pdf", page=12),
        ]
        assert citation_accuracy(extracted_all, expected) == 1.0

        # No extracted citations → vacuous truth → 1.0
        assert citation_accuracy([], expected) == 1.0


class TestHallucinationRate:
    def test_hallucination_rate(self) -> None:
        """Citations to unretrieved files are counted as hallucinated."""
        extracted = [
            ExtractedCitation(filename="complaint.pdf", page=3),
            ExtractedCitation(filename="msa-2024.pdf", page=12),
            ExtractedCitation(filename="phantom.pdf", page=1),
        ]

        retrieved_filenames = {"complaint.pdf", "msa-2024.pdf", "other.docx"}

        # 1 of 3 is hallucinated → rate ≈ 0.333
        rate = hallucination_rate(extracted, retrieved_filenames)
        assert abs(rate - 1 / 3) < 1e-9

        # All retrieved → rate = 0.0
        all_retrieved = {"complaint.pdf", "msa-2024.pdf", "phantom.pdf"}
        assert hallucination_rate(extracted, all_retrieved) == 0.0

        # None retrieved → rate = 1.0
        assert hallucination_rate(extracted, set()) == 1.0

        # No citations → rate = 0.0
        assert hallucination_rate([], retrieved_filenames) == 0.0


class TestPostRationalizationRate:
    def test_post_rationalization_detection(self) -> None:
        """Citations to docs not in fused_context are flagged."""
        extracted = [
            ExtractedCitation(filename="complaint.pdf", page=3),
            ExtractedCitation(filename="memo.docx", page=1),
            ExtractedCitation(filename="email.eml", page=1),
        ]

        # Only complaint.pdf was in the synthesis context
        fused_context = {"complaint.pdf"}

        # 2 of 3 are post-rationalized → rate ≈ 0.667
        rate = post_rationalization_rate(extracted, fused_context)
        assert abs(rate - 2 / 3) < 1e-9

        # All in context → rate = 0.0
        all_context = {"complaint.pdf", "memo.docx", "email.eml"}
        assert post_rationalization_rate(extracted, all_context) == 0.0

        # None in context → rate = 1.0
        assert post_rationalization_rate(extracted, set()) == 1.0

        # No citations → rate = 0.0
        assert post_rationalization_rate([], fused_context) == 0.0
