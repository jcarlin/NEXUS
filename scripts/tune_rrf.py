#!/usr/bin/env python3
"""Sweep RRF prefetch multiplier configurations and report retrieval quality.

Usage::

    python scripts/tune_rrf.py --matter-id <UUID>

Iterates over dense_mult x sparse_mult configurations [1..4] x [1..4],
runs the evaluation pipeline for each, and outputs a comparison table.

Requires:
- Running infrastructure (Qdrant, PostgreSQL)
- Evaluation dataset seeded (scripts/evaluate.py --seed)
- ENABLE_SPARSE_EMBEDDINGS=true
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from itertools import product

# Ensure the app package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def run_sweep(matter_id: str) -> None:
    """Run the dense x sparse multiplier sweep."""
    from app.config import Settings
    from app.dependencies import get_embedder, get_vector_store

    settings = Settings()
    if not settings.enable_sparse_embeddings:
        print("ERROR: ENABLE_SPARSE_EMBEDDINGS must be true for RRF tuning.")
        sys.exit(1)

    vector_store = get_vector_store()
    embedder = get_embedder()

    # Load evaluation questions
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(settings.postgres_url)
    async with engine.begin() as conn:
        result = await conn.execute(
            text("""
                SELECT question, expected_doc_ids
                FROM evaluation_dataset_items
                WHERE matter_id = :matter_id
                LIMIT 50
            """),
            {"matter_id": matter_id},
        )
        items = [dict(r._mapping) for r in result.all()]
    await engine.dispose()

    if not items:
        print("No evaluation dataset items found. Run: python scripts/evaluate.py --seed")
        sys.exit(1)

    multipliers = [1, 2, 3, 4]
    results_table: list[dict] = []

    for dense_mult, sparse_mult in product(multipliers, multipliers):
        total_recall = 0.0
        total_mrr = 0.0
        count = 0

        for item in items:
            question = item["question"]
            expected_ids = item.get("expected_doc_ids", [])
            if not expected_ids:
                continue

            vector = await embedder.embed_query(question)
            hits = await vector_store.query_text(
                vector,
                limit=10,
                filters={"matter_id": matter_id},
                dense_prefetch_multiplier=dense_mult,
                sparse_prefetch_multiplier=sparse_mult,
            )

            hit_ids = [h.get("doc_id", "") for h in hits]

            # Recall@10
            relevant_found = sum(1 for eid in expected_ids if eid in hit_ids)
            recall = relevant_found / len(expected_ids) if expected_ids else 0
            total_recall += recall

            # MRR
            mrr = 0.0
            for rank, hid in enumerate(hit_ids, 1):
                if hid in expected_ids:
                    mrr = 1.0 / rank
                    break
            total_mrr += mrr
            count += 1

        avg_recall = total_recall / count if count else 0
        avg_mrr = total_mrr / count if count else 0

        results_table.append(
            {
                "dense_mult": dense_mult,
                "sparse_mult": sparse_mult,
                "recall@10": round(avg_recall, 4),
                "mrr": round(avg_mrr, 4),
                "queries": count,
            }
        )

        print(f"dense={dense_mult} sparse={sparse_mult} | recall@10={avg_recall:.4f} mrr={avg_mrr:.4f}")

    # Print summary table
    print("\n" + "=" * 60)
    print(f"{'Dense':>6} {'Sparse':>7} {'Recall@10':>10} {'MRR':>8} {'Queries':>8}")
    print("-" * 60)
    for r in sorted(results_table, key=lambda x: x["recall@10"], reverse=True):
        print(f"{r['dense_mult']:>6} {r['sparse_mult']:>7} {r['recall@10']:>10.4f} {r['mrr']:>8.4f} {r['queries']:>8}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Sweep RRF prefetch multiplier configurations")
    parser.add_argument("--matter-id", required=True, help="Matter ID for evaluation")
    args = parser.parse_args()

    asyncio.run(run_sweep(args.matter_id))


if __name__ == "__main__":
    main()
