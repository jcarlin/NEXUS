"""Tests for the heuristic chunk quality scorer."""

from __future__ import annotations

import time

from app.ingestion.quality_scorer import ChunkQualityScore, score_chunk


class TestScoreChunk:
    """Tests for the score_chunk function."""

    def test_high_quality_prose_chunk(self):
        """A full paragraph of legal prose should score > 0.7."""
        text = (
            "On March 15, 2024, John Smith confirmed that the payment of $2.5 million "
            "was made to Acme Corporation as part of the settlement agreement. The funds "
            "were transferred via wire to account ending in 4521. Smith stated that he "
            "personally authorized the transaction after reviewing the terms with outside "
            "counsel. The payment satisfied the obligations under Section 3.2 of the "
            "Merger Agreement dated January 10, 2024."
        )
        result = score_chunk(text, token_count=120)
        assert isinstance(result, ChunkQualityScore)
        assert result.overall > 0.7
        assert result.coherence > 0.6
        assert result.information_density > 0.7

    def test_boilerplate_chunk(self):
        """A chunk of privilege/confidentiality boilerplate should score low."""
        text = (
            "CONFIDENTIAL — PRIVILEGED AND CONFIDENTIAL\n"
            "ATTORNEY-CLIENT PRIVILEGE\n"
            "WORK PRODUCT\n"
            "DO NOT DISTRIBUTE — FOR INTERNAL USE ONLY\n"
            "Page 1 of 47"
        )
        result = score_chunk(text, token_count=30)
        assert result.overall < 0.4
        assert result.information_density < 0.3

    def test_fragment_chunk(self):
        """A truncated sentence fragment should score low on completeness."""
        text = "the payment was authorized by the board on"
        result = score_chunk(text, token_count=10)
        assert result.completeness < 0.8
        assert result.length_score < 0.5  # Very short

    def test_table_only_chunk(self):
        """A chunk that is only a markdown table gets moderate score."""
        text = (
            "| Date | Amount | Description |\n"
            "|------|--------|-------------|\n"
            "| 2024-01-15 | $500,000 | Wire Transfer |\n"
            "| 2024-02-20 | $1,200,000 | Settlement |\n"
            "| 2024-03-10 | $800,000 | Escrow Release |"
        )
        result = score_chunk(text, token_count=60)
        # Tables have value but pure-table chunks are penalized
        assert result.information_density < 0.8

    def test_empty_chunk(self):
        """Empty string scores 0.0 across all dimensions."""
        result = score_chunk("", token_count=0)
        assert result.overall == 0.0
        assert result.coherence == 0.0
        assert result.information_density == 0.0
        assert result.completeness == 0.0
        assert result.length_score == 0.0

    def test_whitespace_only_chunk(self):
        """Whitespace-only chunk scores 0.0."""
        result = score_chunk("   \n\t  \n  ", token_count=0)
        assert result.overall == 0.0

    def test_entity_density_bonus(self):
        """Chunks with high entity count should get an information density boost."""
        # Use text with some boilerplate so base info density isn't already 1.0
        text = "CONFIDENTIAL — John Smith met with Jane Doe at headquarters on March 15."
        result_no_entities = score_chunk(text, token_count=20, entity_count=0)
        result_with_entities = score_chunk(text, token_count=20, entity_count=4)
        assert result_with_entities.information_density > result_no_entities.information_density

    def test_scoring_speed(self):
        """1000 chunks should score in under 1 second."""
        text = (
            "The defendant testified that the meeting occurred on March 15, 2024. "
            "Present were John Smith, Jane Doe, and representatives of Acme Corporation. "
            "The discussion focused on the terms of the proposed settlement."
        )
        start = time.perf_counter()
        for _ in range(1000):
            score_chunk(text, token_count=60)
        elapsed = time.perf_counter() - start
        assert elapsed < 1.0, f"Scoring 1000 chunks took {elapsed:.2f}s (limit: 1.0s)"

    def test_score_ranges(self):
        """All scores should be in [0.0, 1.0] range."""
        texts = [
            "Short.",
            "A" * 5000,
            "| col1 | col2 |\n|---|---|\n| a | b |",
            "CONFIDENTIAL\nPage 1 of 1\n\nIMPORTANT",
            "Normal sentence. Another sentence. A third one.",
        ]
        for text in texts:
            result = score_chunk(text, token_count=len(text.split()))
            for field in ("overall", "coherence", "information_density", "completeness", "length_score"):
                val = getattr(result, field)
                assert 0.0 <= val <= 1.0, f"{field}={val} out of range for text={text[:40]!r}"

    def test_mid_sentence_start_penalty(self):
        """A chunk starting with lowercase (mid-sentence) loses completeness."""
        good = "The defendant confirmed the transaction."
        bad = "the defendant confirmed the transaction."
        good_score = score_chunk(good, token_count=10)
        bad_score = score_chunk(bad, token_count=10)
        assert good_score.completeness > bad_score.completeness

    def test_ideal_length_chunk(self):
        """A chunk with 200 tokens should get max length score."""
        result = score_chunk("Some text.", token_count=200)
        assert result.length_score == 1.0

    def test_very_short_chunk(self):
        """A chunk with <20 tokens should get minimal length score."""
        result = score_chunk("Hi.", token_count=5)
        assert result.length_score == 0.1
