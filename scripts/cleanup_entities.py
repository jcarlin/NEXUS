#!/usr/bin/env python3
"""One-time cleanup: re-normalize existing entities and re-run resolution.

Applies the improved normalize_entity_name() (ftfy-based) to all existing
entities in Neo4j, removes entities that fail the garbage filter, undoes
broken merges (wrongly merged dates/monetary amounts), and re-runs the
improved entity resolution agent.

Usage::

    # Dry run — show proposed changes without modifying anything
    python scripts/cleanup_entities.py \
        --matter-id 00000000-0000-0000-0000-000000000002 --dry-run

    # Execute: re-normalize + delete garbage + undo bad merges
    python scripts/cleanup_entities.py \
        --matter-id 00000000-0000-0000-0000-000000000002

    # After cleanup, re-run entity resolution agent:
    python scripts/cleanup_entities.py \
        --matter-id 00000000-0000-0000-0000-000000000002 --resolve
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Ensure the project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


async def cleanup(matter_id: str, dry_run: bool) -> dict:
    """Re-normalize entities and remove garbage."""
    from neo4j import AsyncGraphDatabase

    from app.config import Settings
    from app.entities.extractor import _is_garbage_entity, normalize_entity_name
    from app.entities.resolver import EXACT_MATCH_TYPES

    settings = Settings()
    driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )

    stats = {"deleted": 0, "renamed": 0, "unmerged": 0, "total": 0}

    try:
        async with driver.session() as session:
            # Phase 1: Fetch all entities for the matter
            result = await session.run(
                "MATCH (e:Entity {matter_id: $mid}) "
                "RETURN e.name AS name, e.type AS type, "
                "e.mention_count AS mc, e.aliases AS aliases",
                {"mid": matter_id},
            )
            records = [r.data() async for r in result]
            stats["total"] = len(records)
            print(f"Found {len(records)} entities in matter {matter_id}")

            # Phase 2: Undo broken merges on exact-match types
            # (dates, monetary amounts were wrongly fuzzy-merged)
            bad_merges = [
                r for r in records if r["type"] in EXACT_MATCH_TYPES and r.get("aliases") and len(r["aliases"]) > 0
            ]
            print(f"Wrongly merged exact-match entities to undo: {len(bad_merges)}")

            for rec in bad_merges:
                if dry_run:
                    print(f"  UNMERGE [{rec['type']}] {rec['name']!r} ({len(rec['aliases'])} aliases)")
                    stats["unmerged"] += len(rec["aliases"])
                else:
                    # Clear the aliases array (we can't reconstruct the merged nodes,
                    # but we stop them from being wrong canonical targets)
                    await session.run(
                        "MATCH (e:Entity {name: $name, type: $type, matter_id: $mid}) SET e.aliases = null",
                        {"name": rec["name"], "type": rec["type"], "mid": matter_id},
                    )
                    stats["unmerged"] += len(rec["aliases"])

            # Phase 3: Re-normalize names and identify garbage
            to_delete: list[tuple[str, str]] = []  # (name, type)
            to_rename: list[tuple[str, str, str]] = []  # (old_name, new_name, type)

            for rec in records:
                old_name = rec["name"]
                new_name = normalize_entity_name(old_name)

                if _is_garbage_entity(new_name):
                    to_delete.append((old_name, rec["type"]))
                elif new_name != old_name:
                    to_rename.append((old_name, new_name, rec["type"]))

            print(f"Garbage entities to delete: {len(to_delete)}")
            print(f"Entities to rename: {len(to_rename)}")

            if dry_run:
                print("\n--- DELETIONS (sample) ---")
                for name, etype in to_delete[:30]:
                    print(f"  DELETE [{etype}] {name!r}")
                if len(to_delete) > 30:
                    print(f"  ... and {len(to_delete) - 30} more")

                print("\n--- RENAMES (sample) ---")
                for old, new, etype in to_rename[:30]:
                    print(f"  RENAME [{etype}] {old!r} -> {new!r}")
                if len(to_rename) > 30:
                    print(f"  ... and {len(to_rename) - 30} more")
            else:
                # Execute deletions
                for name, etype in to_delete:
                    await session.run(
                        "MATCH (e:Entity {name: $name, type: $type, matter_id: $mid}) DETACH DELETE e",
                        {"name": name, "type": etype, "mid": matter_id},
                    )
                    stats["deleted"] += 1

                # Execute renames — check if target name already exists (merge if so)
                for old_name, new_name, etype in to_rename:
                    # Check if an entity with the new name already exists
                    existing = await session.run(
                        "MATCH (e:Entity {name: $name, type: $type, matter_id: $mid}) RETURN e.name AS name",
                        {"name": new_name, "type": etype, "mid": matter_id},
                    )
                    existing_rec = await existing.single()

                    if existing_rec:
                        # Target exists: transfer relationships and delete old
                        await session.run(
                            "MATCH (old:Entity {name: $old, type: $type, matter_id: $mid}), "
                            "      (new:Entity {name: $new, type: $type, matter_id: $mid}) "
                            "SET new.mention_count = coalesce(new.mention_count, 0) + "
                            "    coalesce(old.mention_count, 0) "
                            "WITH old, new "
                            "MATCH (old)-[r]->() "
                            "WITH old, new, collect(r) AS rels "
                            "UNWIND rels AS r "
                            "WITH old, new, r, endNode(r) AS target, type(r) AS rtype "
                            "CALL apoc.create.relationship(new, rtype, properties(r), target) YIELD rel "
                            "WITH old "
                            "DETACH DELETE old",
                            {"old": old_name, "new": new_name, "type": etype, "mid": matter_id},
                        )
                    else:
                        # Simple rename
                        await session.run(
                            "MATCH (e:Entity {name: $old, type: $type, matter_id: $mid}) SET e.name = $new",
                            {"old": old_name, "new": new_name, "type": etype, "mid": matter_id},
                        )
                    stats["renamed"] += 1

    finally:
        await driver.close()

    return stats


async def resolve(matter_id: str) -> dict:
    """Re-run the improved entity resolution agent."""
    from app.entities.resolution_agent import run_resolution_agent

    return await run_resolution_agent(matter_id)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="One-time entity cleanup: re-normalize + remove garbage + re-run resolution"
    )
    parser.add_argument("--matter-id", required=True, help="Matter UUID to process")
    parser.add_argument("--dry-run", action="store_true", help="Show proposed changes without executing")
    parser.add_argument("--resolve", action="store_true", help="Re-run entity resolution agent after cleanup")
    args = parser.parse_args()

    print(f"{'[DRY RUN] ' if args.dry_run else ''}Cleaning up entities for matter {args.matter_id}")
    stats = asyncio.run(cleanup(args.matter_id, args.dry_run))

    print(f"\nCleanup {'preview' if args.dry_run else 'complete'}:")
    print(f"  Total entities: {stats['total']}")
    print(f"  Deleted (garbage): {stats['deleted']}")
    print(f"  Renamed (normalized): {stats['renamed']}")
    print(f"  Unmerged (bad merges): {stats['unmerged']}")

    if args.resolve and not args.dry_run:
        print("\nRunning entity resolution agent...")
        result = asyncio.run(resolve(args.matter_id))
        print(f"Resolution complete: {result}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
