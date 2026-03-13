"""Re-embed existing Qdrant collection with named dense + sparse vectors.

This script migrates a `nexus_text` collection from unnamed single-vector
format to named vectors (``dense`` + ``sparse``).  It:

1. Scrolls all existing points from ``nexus_text`` (batched).
2. Deletes and recreates the collection with named vector config.
3. Generates sparse embeddings from ``chunk_text`` in each point's payload.
4. Re-upserts all points with named vectors (dense + sparse).

Pre-production only — uses delete + recreate (not in-place migration).
Idempotent: safe to run multiple times.

Usage::

    python scripts/reembed.py [--batch-size 100] [--dry-run]
"""

from __future__ import annotations

import argparse
import time

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    PointStruct,
    SparseVector,
    SparseVectorParams,
    VectorParams,
)

from app.config import Settings
from app.ingestion.sparse_embedder import SparseEmbedder

COLLECTION = "nexus_text"


def _scroll_all(client: QdrantClient, batch_size: int) -> list[dict]:
    """Scroll all points from the collection, returning list of dicts."""
    points: list[dict] = []
    offset = None

    while True:
        result = client.scroll(
            collection_name=COLLECTION,
            limit=batch_size,
            offset=offset,
            with_payload=True,
            with_vectors=True,
        )
        batch, next_offset = result

        for point in batch:
            # Extract the dense vector — handle both named and unnamed formats
            vector = point.vector
            if isinstance(vector, dict):
                vector = vector.get("dense", vector)

            points.append(
                {
                    "id": point.id,
                    "vector": vector,
                    "payload": point.payload,
                }
            )

        if next_offset is None:
            break
        offset = next_offset

    return points


def main() -> None:
    parser = argparse.ArgumentParser(description="Re-embed nexus_text with named dense + sparse vectors")
    parser.add_argument("--batch-size", type=int, default=100, help="Scroll/upsert batch size")
    parser.add_argument("--dry-run", action="store_true", help="Scroll and embed but don't modify collection")
    parser.add_argument(
        "--provider",
        choices=["bm42", "bgem3"],
        default="bm42",
        help="Sparse embedding provider (bm42=FastEmbed BM42, bgem3=BGE-M3 unified dense+sparse)",
    )
    args = parser.parse_args()

    settings = Settings()
    client = QdrantClient(url=settings.qdrant_url)

    use_bgem3 = args.provider == "bgem3"
    sparse_embedder = None
    bgem3_provider = None

    if use_bgem3:
        from app.common.embedder import BGEM3Provider

        bgem3_provider = BGEM3Provider(
            model_name=settings.bgem3_model_name,
            max_length=settings.bgem3_max_length,
            batch_size=settings.bgem3_batch_size,
            use_fp16=settings.bgem3_use_fp16,
        )
    else:
        sparse_embedder = SparseEmbedder(model_name=settings.sparse_embedding_model)

    # Step 1: Scroll all existing points
    print(f"Scrolling all points from '{COLLECTION}' (batch_size={args.batch_size})...")
    t0 = time.time()
    points = _scroll_all(client, args.batch_size)
    print(f"  Found {len(points)} points in {time.time() - t0:.1f}s")

    if not points:
        print("No points to migrate. Done.")
        return

    # Step 2: Generate embeddings
    texts = [p["payload"].get("chunk_text", "") for p in points]

    dense_vectors: list[list[float]] | None = None
    sparse_vectors: list[tuple[list[int], list[float]]] = []

    if use_bgem3:
        import asyncio

        print("Generating unified dense + sparse embeddings (BGE-M3)...")
        t0 = time.time()
        for i in range(0, len(texts), args.batch_size):
            batch = texts[i : i + args.batch_size]
            batch_dense, batch_sparse = asyncio.run(bgem3_provider.embed_all(batch))
            if dense_vectors is None:
                dense_vectors = batch_dense
            else:
                dense_vectors.extend(batch_dense)
            sparse_vectors.extend(batch_sparse)
            print(f"  Embedded {min(i + args.batch_size, len(texts))}/{len(texts)}")
        print(f"  BGE-M3 embeddings generated in {time.time() - t0:.1f}s")
    else:
        print("Generating sparse embeddings...")
        t0 = time.time()
        for i in range(0, len(texts), args.batch_size):
            batch = texts[i : i + args.batch_size]
            sparse_vectors.extend(sparse_embedder.embed_texts(batch))
            print(f"  Embedded {min(i + args.batch_size, len(texts))}/{len(texts)}")
        print(f"  Sparse embeddings generated in {time.time() - t0:.1f}s")

    if args.dry_run:
        print("[DRY RUN] Would delete and recreate collection, then upsert all points.")
        print(f"  Sample sparse vector: indices={sparse_vectors[0][0][:5]}... values={sparse_vectors[0][1][:5]}...")
        return

    # Step 3: Delete and recreate collection with named vectors
    print(f"Recreating '{COLLECTION}' with named dense + sparse vectors...")
    client.delete_collection(COLLECTION)
    client.create_collection(
        collection_name=COLLECTION,
        vectors_config={
            "dense": VectorParams(
                size=settings.embedding_dimensions,
                distance=Distance.COSINE,
            ),
        },
        sparse_vectors_config={
            "sparse": SparseVectorParams(),
        },
    )
    print("  Collection recreated.")

    # Step 4: Re-upsert with named vectors
    print("Re-upserting points with named vectors...")
    t0 = time.time()
    for i in range(0, len(points), args.batch_size):
        batch_points = points[i : i + args.batch_size]
        batch_sparse = sparse_vectors[i : i + args.batch_size]

        qdrant_points = []
        for j, (p, (indices, values)) in enumerate(zip(batch_points, batch_sparse)):
            # Use new dense vectors from BGE-M3 or keep existing ones
            point_dense = dense_vectors[i + j] if dense_vectors else p["vector"]
            qdrant_points.append(
                PointStruct(
                    id=p["id"],
                    vector={
                        "dense": point_dense,
                        "sparse": SparseVector(indices=indices, values=values),
                    },
                    payload=p["payload"],
                )
            )

        client.upsert(collection_name=COLLECTION, points=qdrant_points)
        print(f"  Upserted {min(i + args.batch_size, len(points))}/{len(points)}")

    print(f"  Done in {time.time() - t0:.1f}s")
    print(f"Migration complete: {len(points)} points migrated to named vectors.")


if __name__ == "__main__":
    main()
