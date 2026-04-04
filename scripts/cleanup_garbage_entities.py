#!/usr/bin/env python3
"""Delete garbage entities from Neo4j knowledge graph.

Tiered cleanup with dry-run default and JSONL audit log.
Uses two-phase batch deletion (relationships first, then naked nodes)
to avoid Neo4j OOM on high-degree nodes.

Tiers:
  1 — Auto-delete (zero false-positive risk): emails-as-persons,
      email-domains-as-orgs, <=2 char persons, numeric-only, possessives,
      bare suffixes, social handles, >50 char persons
  2 — Safe with review: orgs misclassified as persons, products-as-orgs

Usage::

    # Dry-run all tiers (default)
    python scripts/cleanup_garbage_entities.py

    # Dry-run specific category
    python scripts/cleanup_garbage_entities.py --category email-persons

    # Execute tier 1 only
    python scripts/cleanup_garbage_entities.py --tier 1 --execute

    # Execute all tiers
    python scripts/cleanup_garbage_entities.py --execute
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DEFAULT_MATTER_ID = "00000000-0000-0000-0000-000000000002"
DEFAULT_BATCH = 500
AUDIT_LOG_DIR = Path(os.environ.get("NEXUS_AUDIT_DIR", str(Path(__file__).resolve().parent.parent / "reports")))

# --- Category definitions ---
# Each category: (name, tier, description, cypher_match, cypher_params_fn)


def _categories(matter_id: str) -> list[dict]:
    """Return all garbage categories with their Cypher match clauses."""
    mid = matter_id
    return [
        # Tier 1 — zero false-positive risk
        {
            "name": "email-persons",
            "tier": 1,
            "description": "Email addresses misclassified as persons",
            "match": "MATCH (e:Entity {type: 'person', matter_id: $mid}) WHERE e.name CONTAINS '@'",
            "params": {"mid": mid},
        },
        {
            "name": "email-domains-orgs",
            "tier": 1,
            "description": "Email domains misclassified as organizations",
            "match": (
                "MATCH (e:Entity {type: 'organization', matter_id: $mid}) "
                "WHERE (e.name ENDS WITH '.com' OR e.name ENDS WITH '.org' "
                "OR e.name ENDS WITH '.net' OR e.name ENDS WITH '.gov' "
                "OR e.name ENDS WITH '.edu' OR e.name ENDS WITH '.io') "
                "AND NOT (e.name CONTAINS 'Amazon' AND NOT e.name ENDS WITH '.com') "
                "AND size(e.name) <= 40"
            ),
            "params": {"mid": mid},
        },
        {
            "name": "short-persons",
            "tier": 1,
            "description": "Person entities <= 2 characters (initials/garbage)",
            "match": "MATCH (e:Entity {type: 'person', matter_id: $mid}) WHERE size(e.name) <= 2",
            "params": {"mid": mid},
        },
        {
            "name": "numeric-only",
            "tier": 1,
            "description": "Entities with purely numeric names",
            "match": "MATCH (e:Entity {matter_id: $mid}) WHERE e.name =~ '^[0-9.,\\\\s]+$'",
            "params": {"mid": mid},
        },
        {
            "name": "possessives",
            "tier": 1,
            "description": "Person entities ending with possessive 's",
            "match": (
                "MATCH (e:Entity {type: 'person', matter_id: $mid}) "
                'WHERE e.name ENDS WITH "\'s" OR e.name ENDS WITH "\'s"'
            ),
            "params": {"mid": mid},
        },
        {
            "name": "bare-suffixes",
            "tier": 1,
            "description": "Organization entities that are just legal suffixes",
            "match": (
                "MATCH (e:Entity {type: 'organization', matter_id: $mid}) "
                "WHERE e.name IN ['LLC', 'Inc.', 'Inc', 'Corp.', 'Corp', 'L.L.C.', "
                "'Co.', 'Ltd.', 'Ltd', 'N.A.', 'P.C.', 'LLP']"
            ),
            "params": {"mid": mid},
        },
        {
            "name": "long-persons",
            "tier": 1,
            "description": "Person entities > 50 chars (concatenated OCR garbage)",
            "match": "MATCH (e:Entity {type: 'person', matter_id: $mid}) WHERE size(e.name) > 50",
            "params": {"mid": mid},
        },
        # Tier 2 — safe with review
        {
            "name": "org-as-person",
            "tier": 2,
            "description": "Organizations misclassified as persons (Foundation/Inc/LLC/Corp)",
            "match": (
                "MATCH (e:Entity {type: 'person', matter_id: $mid}) "
                "WHERE e.name CONTAINS 'Foundation' OR e.name CONTAINS 'Inc.' "
                "OR e.name CONTAINS ' LLC' OR e.name CONTAINS 'Corp.' "
                "OR e.name CONTAINS 'Company' OR e.name CONTAINS 'Association' "
                "OR e.name CONTAINS 'Committee' OR e.name CONTAINS 'Department'"
            ),
            "params": {"mid": mid},
        },
    ]


def _count_category(session, cat: dict) -> int:
    """Count entities matching a category."""
    result = session.run(
        f"{cat['match']} RETURN count(e) AS cnt",
        **cat["params"],
    )
    return result.single()["cnt"]


def _list_category(session, cat: dict, limit: int = 50) -> list[dict]:
    """List sample entities for a category."""
    result = session.run(
        f"{cat['match']} "
        "WITH e "
        "OPTIONAL MATCH (e)-[r:MENTIONED_IN]->() "
        "WITH e, count(r) AS mentions "
        "RETURN e.name AS name, e.type AS type, mentions "
        "ORDER BY mentions DESC LIMIT $limit",
        **cat["params"],
        limit=limit,
    )
    return [dict(r) for r in result]


def _delete_category(
    session_factory,
    cat: dict,
    batch_size: int,
    audit_file,
) -> tuple[int, int]:
    """Delete entities for a category using two-phase batch deletion.

    Returns (relationships_deleted, nodes_deleted).
    """
    total_rels = 0
    total_nodes = 0

    # Phase 1: delete relationships in batches
    while True:
        try:
            with session_factory() as s:
                result = s.run(
                    f"{cat['match']} WITH e LIMIT $batch MATCH (e)-[r]-() DELETE r RETURN count(*) AS deleted",
                    **cat["params"],
                    batch=batch_size,
                )
                deleted = result.single()["deleted"]
                total_rels += deleted
                if deleted < batch_size:
                    break
        except Exception as e:
            err = str(e)[:200]
            print(f"    Rel error (retrying in 3s): {err}", flush=True)
            time.sleep(3)

    # Phase 2: delete naked nodes in batches, logging each
    while True:
        try:
            with session_factory() as s:
                result = s.run(
                    f"{cat['match']} "
                    "WHERE NOT (e)--() "
                    "WITH e LIMIT $batch "
                    "WITH e, e.name AS name, e.type AS type "
                    "DELETE e RETURN name, type",
                    **cat["params"],
                    batch=batch_size,
                )
                records = list(result)
                for r in records:
                    audit_entry = {
                        "ts": datetime.now(UTC).isoformat(),
                        "category": cat["name"],
                        "name": r["name"],
                        "type": r["type"],
                        "action": "deleted",
                    }
                    audit_file.write(json.dumps(audit_entry) + "\n")
                total_nodes += len(records)
                if len(records) < batch_size:
                    break
        except Exception as e:
            err = str(e)[:200]
            print(f"    Node error (retrying in 3s): {err}", flush=True)
            time.sleep(3)

    return total_rels, total_nodes


def main() -> None:
    parser = argparse.ArgumentParser(description="Delete garbage entities from Neo4j")
    parser.add_argument("--matter-id", default=DEFAULT_MATTER_ID)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH)
    parser.add_argument("--tier", type=int, choices=[1, 2], help="Only run this tier")
    parser.add_argument("--category", help="Only run this category (e.g., email-persons)")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually delete (default is dry-run)",
    )
    parser.add_argument(
        "--show-samples",
        action="store_true",
        help="Show sample entities per category in dry-run",
    )
    args = parser.parse_args()

    from app.config import Settings

    settings = Settings()

    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )

    categories = _categories(args.matter_id)

    # Filter by tier or category
    if args.category:
        categories = [c for c in categories if c["name"] == args.category]
        if not categories:
            print(f"Unknown category: {args.category}")
            print("Available:", ", ".join(c["name"] for c in _categories(args.matter_id)))
            sys.exit(1)
    elif args.tier:
        categories = [c for c in categories if c["tier"] == args.tier]

    if not args.execute:
        # Dry-run mode
        print("=== DRY RUN (pass --execute to delete) ===\n")
        with driver.session() as s:
            grand_total = 0
            for cat in categories:
                cnt = _count_category(s, cat)
                grand_total += cnt
                tier_label = f"[Tier {cat['tier']}]"
                print(f"  {tier_label} {cat['name']}: {cnt:,} entities — {cat['description']}")
                if args.show_samples and cnt > 0:
                    samples = _list_category(s, cat, limit=10)
                    for sample in samples:
                        print(f"         {sample['name']!r} ({sample['type']}, {sample['mentions']} mentions)")
            print(f"\n  Total: {grand_total:,} entities would be deleted")
        driver.close()
        return

    # Execute mode
    AUDIT_LOG_DIR.mkdir(parents=True, exist_ok=True)
    audit_path = AUDIT_LOG_DIR / f"entity_cleanup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"

    print(f"=== EXECUTING CLEANUP (audit log: {audit_path}) ===\n")
    t0 = time.time()
    grand_rels = 0
    grand_nodes = 0

    with open(audit_path, "w") as audit_file:
        for cat in categories:
            with driver.session() as s:
                cnt = _count_category(s, cat)
            if cnt == 0:
                print(f"  [{cat['name']}] 0 entities, skipping")
                continue

            print(f"  [{cat['name']}] Deleting {cnt:,} entities — {cat['description']}...", flush=True)
            rels, nodes = _delete_category(
                driver.session,
                cat,
                args.batch_size,
                audit_file,
            )
            grand_rels += rels
            grand_nodes += nodes
            elapsed = time.time() - t0
            print(f"    Done: {rels:,} rels + {nodes:,} nodes ({elapsed:.0f}s total)", flush=True)

    driver.close()
    elapsed = time.time() - t0
    print(f"\n=== COMPLETE: {grand_rels:,} rels + {grand_nodes:,} nodes deleted in {elapsed:.0f}s ===")
    print(f"Audit log: {audit_path}")


if __name__ == "__main__":
    main()
