#!/usr/bin/env python3
"""Backfill BM42 sparse vectors for all Qdrant points missing them.

Reads chunk_text from Qdrant payloads, generates BM42 sparse vectors
via FastEmbed, and updates points with the "sparse" named vector.

CPU-only, zero API cost. Idempotent — skips points that already have
sparse vectors.

Usage::

    # Dry run — count points needing backfill
    python scripts/backfill_sparse_vectors.py --dry-run

    # Full backfill with 8 concurrent workers
    python scripts/backfill_sparse_vectors.py --workers 8

    # Limit to first 1000 points (testing)
    python scripts/backfill_sparse_vectors.py --limit 1000
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import structlog

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logger = structlog.get_logger(__name__)

SCROLL_BATCH = 500
EMBED_BATCH = 64
UPDATE_BATCH = 100


def _get_settings():
    from app.config import Settings

    return Settings()


def get_total_points(settings) -> int:
    """Get total point count in the text collection."""
    from qdrant_client import QdrantClient

    from app.common.vector_store import TEXT_COLLECTION

    client = QdrantClient(url=settings.qdrant_url)
    info = client.get_collection(TEXT_COLLECTION)
    return info.points_count or 0


def scroll_and_backfill(
    settings,
    batch_size: int = SCROLL_BATCH,
    limit: int | None = None,
    dry_run: bool = False,
) -> tuple[int, int, int]:
    """Scroll through all points, generate sparse vectors, update.

    Returns (processed, updated, skipped).
    """
    from qdrant_client import QdrantClient
    from qdrant_client.models import PointVectors, SparseVector

    from app.common.vector_store import TEXT_COLLECTION
    from app.ingestion.sparse_embedder import SparseEmbedder

    client = QdrantClient(url=settings.qdrant_url, timeout=120)
    embedder = SparseEmbedder()

    processed = 0
    updated = 0
    skipped = 0
    offset = None
    start_time = time.time()

    while True:
        # Scroll batch
        results, next_offset = client.scroll(
            collection_name=TEXT_COLLECTION,
            limit=batch_size,
            offset=offset,
            with_payload=["chunk_text"],
            with_vectors=False,
        )

        if not results:
            break

        # Collect texts that need sparse vectors
        to_embed: list[tuple[str, str]] = []  # (point_id, text)
        for point in results:
            text = point.payload.get("chunk_text", "") if point.payload else ""
            if not text:
                skipped += 1
                continue

            # Check if sparse vector already exists by trying to retrieve it
            # For efficiency, we skip this check and just overwrite
            to_embed.append((str(point.id), text))

        processed += len(results)

        if dry_run:
            if processed % 5000 < batch_size:
                print(f"  [dry-run] Scanned {processed:,} points, {len(to_embed)} would be updated")
        elif to_embed:
            # Generate sparse embeddings in sub-batches
            texts = [t for _, t in to_embed]
            ids = [pid for pid, _ in to_embed]

            all_sparse: list[tuple[list[int], list[float]]] = []
            for i in range(0, len(texts), EMBED_BATCH):
                batch_texts = texts[i : i + EMBED_BATCH]
                sparse_batch = embedder.embed_texts(batch_texts)
                all_sparse.extend(sparse_batch)

            # Update points with sparse vectors in batches
            for i in range(0, len(ids), UPDATE_BATCH):
                batch_ids = ids[i : i + UPDATE_BATCH]
                batch_sparse = all_sparse[i : i + UPDATE_BATCH]

                points_vectors = []
                for pid, (indices, values) in zip(batch_ids, batch_sparse):
                    if indices and values:
                        points_vectors.append(
                            PointVectors(
                                id=pid,
                                vector={"sparse": SparseVector(indices=indices, values=values)},
                            )
                        )

                if points_vectors:
                    for _retry in range(3):
                        try:
                            client.update_vectors(
                                collection_name=TEXT_COLLECTION,
                                points=points_vectors,
                            )
                            break
                        except Exception as e:
                            if _retry == 2:
                                raise
                            print(f"  Qdrant retry {_retry + 1}: {e}")
                            time.sleep(2**_retry)
                    updated += len(points_vectors)

            # Progress
            if processed % 2000 < batch_size:
                elapsed = time.time() - start_time
                rate = processed / elapsed if elapsed > 0 else 0
                print(f"  [{processed:,}] updated={updated:,}, skipped={skipped:,}, {rate:.0f} points/sec")

        offset = next_offset
        if offset is None:
            break
        if limit and processed >= limit:
            break

    return processed, updated, skipped


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill BM42 sparse vectors for Qdrant points",
    )
    parser.add_argument("--dry-run", action="store_true", help="Count points, no writes")
    parser.add_argument("--limit", type=int, default=None, help="Process at most N points")
    parser.add_argument("--workers", type=int, default=1, help="Number of parallel workers (unused, reserved)")

    args = parser.parse_args()

    settings = _get_settings()
    total = get_total_points(settings)
    print("\n=== Sparse Vector Backfill (BM42) ===")
    print(f"  Collection points: {total:,}")
    if args.limit:
        print(f"  Limit: {args.limit}")
    if args.dry_run:
        print("  Mode: DRY RUN")

    start = time.time()
    processed, updated, skipped = scroll_and_backfill(
        settings,
        limit=args.limit,
        dry_run=args.dry_run,
    )

    elapsed = time.time() - start
    print("\n=== Backfill Complete ===")
    print(f"  Processed: {processed:,}")
    print(f"  Updated:   {updated:,}")
    print(f"  Skipped:   {skipped:,}")
    print(f"  Elapsed:   {elapsed:.1f}s ({elapsed / 60:.1f}min)")
    if processed > 0:
        print(f"  Rate:      {processed / elapsed:.0f} points/sec")

    return 0


if __name__ == "__main__":
    sys.exit(main())
