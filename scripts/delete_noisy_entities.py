#!/usr/bin/env python3
"""Delete noisy entity types from Neo4j (reference_number, phone_number, email_address).

Two-phase approach to avoid Neo4j OOM on DETACH DELETE:
1. Delete relationships in small batches
2. Delete naked (relationship-free) nodes in small batches

Idempotent — safe to re-run if interrupted.

Usage::

    python scripts/delete_noisy_entities.py
    python scripts/delete_noisy_entities.py --batch-size 200
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

TYPES_TO_DELETE = ["reference_number", "phone_number", "email_address"]
DEFAULT_MATTER_ID = "00000000-0000-0000-0000-000000000002"
DEFAULT_BATCH = 500


def main() -> None:
    parser = argparse.ArgumentParser(description="Delete noisy entity types from Neo4j")
    parser.add_argument("--matter-id", default=DEFAULT_MATTER_ID)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    from app.config import Settings

    settings = Settings()

    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )

    mid = args.matter_id
    batch = args.batch_size

    if args.dry_run:
        with driver.session() as s:
            for etype in TYPES_TO_DELETE:
                result = s.run(
                    "MATCH (e:Entity {type: $type, matter_id: $mid}) RETURN count(e) AS cnt",
                    type=etype,
                    mid=mid,
                )
                cnt = result.single()["cnt"]
                print(f"  {etype}: {cnt:,} entities would be deleted")
        driver.close()
        return

    total_rels = 0
    total_nodes = 0
    t0 = time.time()

    for etype in TYPES_TO_DELETE:
        # Phase 1: delete relationships
        print(f"\n--- Deleting relationships for {etype} ---", flush=True)
        while True:
            try:
                with driver.session() as s:
                    result = s.run(
                        "MATCH (e:Entity {type: $type, matter_id: $mid})-[r]-() "
                        "WITH r LIMIT $batch DELETE r RETURN count(*) AS deleted",
                        type=etype,
                        mid=mid,
                        batch=batch,
                    )
                    deleted = result.single()["deleted"]
                    total_rels += deleted
                    if total_rels % 50000 < batch:
                        elapsed = time.time() - t0
                        print(f"  rels: {total_rels:,} ({elapsed:.0f}s)", flush=True)
                    if deleted < batch:
                        break
            except Exception as e:
                err = str(e)[:120]
                print(f"  Rel error (retrying): {err}", flush=True)
                time.sleep(3)

        # Phase 2: delete naked nodes
        print(f"\n--- Deleting nodes for {etype} ---", flush=True)
        while True:
            try:
                with driver.session() as s:
                    result = s.run(
                        "MATCH (e:Entity {type: $type, matter_id: $mid}) "
                        "WHERE NOT (e)--() "
                        "WITH e LIMIT $batch DELETE e RETURN count(*) AS deleted",
                        type=etype,
                        mid=mid,
                        batch=batch,
                    )
                    deleted = result.single()["deleted"]
                    total_nodes += deleted
                    if total_nodes % 50000 < batch:
                        elapsed = time.time() - t0
                        print(f"  nodes: {total_nodes:,} ({elapsed:.0f}s)", flush=True)
                    if deleted < batch:
                        break
            except Exception as e:
                err = str(e)[:120]
                print(f"  Node error (retrying): {err}", flush=True)
                time.sleep(3)

    driver.close()
    elapsed = time.time() - t0
    print(f"\nDone: {total_rels:,} rels + {total_nodes:,} nodes deleted in {elapsed:.0f}s")


if __name__ == "__main__":
    main()
