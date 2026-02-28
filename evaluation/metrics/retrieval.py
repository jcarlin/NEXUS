"""Retrieval quality metrics: MRR, Recall, NDCG, Precision at k.

Pure functions with zero external dependencies.
"""

from __future__ import annotations

import math


def mrr_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int = 10) -> float:
    """Mean Reciprocal Rank at k.

    Returns 1/rank of the first relevant document in the top-k results,
    or 0.0 if no relevant document is found.
    """
    for i, doc_id in enumerate(retrieved_ids[:k]):
        if doc_id in relevant_ids:
            return 1.0 / (i + 1)
    return 0.0


def recall_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int = 10) -> float:
    """Recall at k: fraction of relevant documents found in top-k.

    Returns 0.0 if there are no relevant documents.
    """
    if not relevant_ids:
        return 0.0
    found = sum(1 for doc_id in retrieved_ids[:k] if doc_id in relevant_ids)
    return found / len(relevant_ids)


def precision_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int = 10) -> float:
    """Precision at k: fraction of top-k results that are relevant.

    Returns 0.0 if k is 0.
    """
    if k == 0:
        return 0.0
    top_k = retrieved_ids[:k]
    relevant_count = sum(1 for doc_id in top_k if doc_id in relevant_ids)
    return relevant_count / k


def ndcg_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int = 10) -> float:
    """Normalized Discounted Cumulative Gain at k (binary relevance).

    DCG = sum(rel_i / log2(i+2)) for i in 0..k-1
    IDCG = DCG of ideal ranking (all relevant docs first)
    NDCG = DCG / IDCG

    Returns 0.0 if there are no relevant documents.
    """
    if not relevant_ids:
        return 0.0

    # DCG of actual ranking
    dcg = 0.0
    for i, doc_id in enumerate(retrieved_ids[:k]):
        if doc_id in relevant_ids:
            dcg += 1.0 / math.log2(i + 2)

    # IDCG: ideal ranking has min(|relevant|, k) relevant docs at top
    ideal_count = min(len(relevant_ids), k)
    idcg = sum(1.0 / math.log2(i + 2) for i in range(ideal_count))

    if idcg == 0.0:
        return 0.0

    return dcg / idcg


def compute_retrieval_metrics(
    retrieved_ids: list[str],
    relevant_ids: set[str],
    k: int = 10,
) -> dict[str, float]:
    """Compute all four retrieval metrics and return as a dict."""
    return {
        "mrr_at_k": mrr_at_k(retrieved_ids, relevant_ids, k),
        "recall_at_k": recall_at_k(retrieved_ids, relevant_ids, k),
        "precision_at_k": precision_at_k(retrieved_ids, relevant_ids, k),
        "ndcg_at_k": ndcg_at_k(retrieved_ids, relevant_ids, k),
    }
