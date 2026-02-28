"""Tests for retrieval quality metrics."""

from __future__ import annotations

from evaluation.metrics.retrieval import (
    mrr_at_k,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
)


class TestMRRAtK:
    def test_mrr_at_10(self) -> None:
        """MRR=1.0 at rank 1; MRR=0.5 at rank 2; MRR=0.0 when absent."""
        relevant = {"doc-a", "doc-b"}

        # Relevant doc at rank 1 → MRR = 1.0
        retrieved = ["doc-a", "doc-c", "doc-d"]
        assert mrr_at_k(retrieved, relevant, k=10) == 1.0

        # Relevant doc at rank 2 → MRR = 0.5
        retrieved = ["doc-c", "doc-a", "doc-d"]
        assert mrr_at_k(retrieved, relevant, k=10) == 0.5

        # Relevant doc at rank 3 → MRR = 1/3
        retrieved = ["doc-c", "doc-d", "doc-b"]
        assert abs(mrr_at_k(retrieved, relevant, k=10) - 1 / 3) < 1e-9

        # No relevant docs → MRR = 0.0
        retrieved = ["doc-c", "doc-d", "doc-e"]
        assert mrr_at_k(retrieved, relevant, k=10) == 0.0

        # Empty retrieval → MRR = 0.0
        assert mrr_at_k([], relevant, k=10) == 0.0


class TestRecallAtK:
    def test_recall_at_10(self) -> None:
        """Recall=0.5 for 1/2 found; Recall=1.0 for all found."""
        relevant = {"doc-a", "doc-b"}

        # 1 of 2 found → Recall = 0.5
        retrieved = ["doc-a", "doc-c", "doc-d", "doc-e", "doc-f"]
        assert recall_at_k(retrieved, relevant, k=10) == 0.5

        # 2 of 2 found → Recall = 1.0
        retrieved = ["doc-a", "doc-b", "doc-c"]
        assert recall_at_k(retrieved, relevant, k=10) == 1.0

        # 0 of 2 found → Recall = 0.0
        retrieved = ["doc-c", "doc-d"]
        assert recall_at_k(retrieved, relevant, k=10) == 0.0

        # Empty relevant set → Recall = 0.0
        assert recall_at_k(["doc-a"], set(), k=10) == 0.0


class TestNDCGAtK:
    def test_ndcg_at_10(self) -> None:
        """NDCG=1.0 for perfect ranking; lower for imperfect."""
        relevant = {"doc-a", "doc-b"}

        # Perfect ranking: both relevant docs at top
        retrieved = ["doc-a", "doc-b", "doc-c", "doc-d"]
        assert abs(ndcg_at_k(retrieved, relevant, k=10) - 1.0) < 1e-9

        # Imperfect: relevant doc at position 2, not 1
        retrieved = ["doc-c", "doc-a", "doc-b", "doc-d"]
        ndcg = ndcg_at_k(retrieved, relevant, k=10)
        assert 0.0 < ndcg < 1.0

        # No relevant docs → NDCG = 0.0
        retrieved = ["doc-c", "doc-d", "doc-e"]
        assert ndcg_at_k(retrieved, relevant, k=10) == 0.0

        # Empty relevant set → NDCG = 0.0
        assert ndcg_at_k(["doc-a"], set(), k=10) == 0.0

        # Verify imperfect is lower than perfect
        perfect = ["doc-a", "doc-b", "doc-c"]
        imperfect = ["doc-c", "doc-a", "doc-b"]
        assert ndcg_at_k(perfect, relevant, k=10) > ndcg_at_k(imperfect, relevant, k=10)


class TestPrecisionAtK:
    def test_precision_at_10(self) -> None:
        """Precision=0.3 for 3/10 relevant; 0.0 for none."""
        relevant = {"doc-a", "doc-b", "doc-c"}

        # 3 relevant in top 10
        retrieved = [
            "doc-a",
            "doc-x",
            "doc-b",
            "doc-y",
            "doc-c",
            "doc-z",
            "doc-w",
            "doc-v",
            "doc-u",
            "doc-t",
        ]
        assert abs(precision_at_k(retrieved, relevant, k=10) - 0.3) < 1e-9

        # 0 relevant in top 10
        retrieved = [f"noise-{i}" for i in range(10)]
        assert precision_at_k(retrieved, relevant, k=10) == 0.0

        # All relevant in top 3, k=3 → Precision = 1.0
        retrieved = ["doc-a", "doc-b", "doc-c"]
        assert precision_at_k(retrieved, relevant, k=3) == 1.0

        # k=0 → Precision = 0.0
        assert precision_at_k(retrieved, relevant, k=0) == 0.0
