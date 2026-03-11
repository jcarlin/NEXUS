"""Wipe all NEXUS data stores for a clean re-ingest.

Clears: PostgreSQL (data tables), Qdrant (all points), Neo4j (all nodes), MinIO (document objects), Redis.
Preserves: users, case_matters, user_case_matters, audit_log, ai_audit_log, datasets table structure.

With --drop-db: drops and recreates the entire PostgreSQL schema, then runs alembic upgrade head.

Usage:
    python scripts/wipe_data.py            # truncate data tables only
    python scripts/wipe_data.py --drop-db  # full PG nuke + re-migrate
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv
except ImportError:
    pass
else:
    load_dotenv()

from sqlalchemy import create_engine, text

from app.config import Settings


def wipe_postgres(settings: Settings, *, drop_db: bool = False) -> None:
    """Delete data tables in dependency order, preserving users/matters/audit."""
    print("=== Wiping PostgreSQL ===")
    engine = create_engine(settings.postgres_url_sync, pool_pre_ping=True)

    if drop_db:
        print("  --drop-db: dropping entire public schema...")
        with engine.connect() as conn:
            conn.execute(text("DROP SCHEMA public CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
            conn.commit()
        print("  Schema dropped and recreated")
        engine.dispose()

        print("  Running alembic upgrade head...")
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"  Alembic failed:\n{result.stderr}")
            sys.exit(1)
        print("  Alembic migrations applied")
        print("  PostgreSQL wiped (full reset)\n")
        return

    # Dependency order: children first
    tables_to_clear = [
        "chat_messages",
        "evaluation_runs",
        "evaluation_dataset_items",
        "dataset_documents",
        "document_tags",
        "dataset_access",
        "case_defined_terms",
        "case_parties",
        "case_claims",
        "case_contexts",
        "communication_pairs",
        "org_chart_entries",
        "investigation_sessions",
        "annotations",
        "production_set_documents",
        "production_sets",
        "export_jobs",
        "redactions",
        "edrm_import_log",
        "bulk_import_jobs",
        "memos",
        "google_drive_sync_state",
        "google_drive_connections",
        "jobs",
        "documents",
    ]

    with engine.connect() as conn:
        # Use TRUNCATE CASCADE for tables with FK dependencies
        try:
            conn.execute(text("TRUNCATE TABLE " + ", ".join(tables_to_clear) + " CASCADE"))
            print(f"  Truncated {len(tables_to_clear)} tables (CASCADE)")
        except Exception as exc:
            conn.rollback()
            print(f"  TRUNCATE failed ({exc}), falling back to DELETE...")
            for table in tables_to_clear:
                try:
                    result = conn.execute(text(f"DELETE FROM {table}"))  # noqa: S608
                    conn.commit()
                    print(f"  {table}: {result.rowcount} rows deleted")
                except Exception as exc2:
                    conn.rollback()
                    print(f"  {table}: skipped ({exc2.__class__.__name__})")
        # Also clear LangGraph checkpointer tables if they exist
        for table in ["checkpoint_blobs", "checkpoint_writes", "checkpoints"]:
            try:
                result = conn.execute(text(f"TRUNCATE TABLE {table} CASCADE"))  # noqa: S608
                print(f"  {table}: truncated")
            except Exception:
                pass
        conn.commit()
    print("  PostgreSQL wiped\n")


def wipe_qdrant(settings: Settings) -> None:
    """Delete all points from Qdrant collections (preserves collection structure)."""
    print("=== Wiping Qdrant ===")
    try:
        from qdrant_client import QdrantClient
        from qdrant_client.models import FilterSelector, models

        client = QdrantClient(url=settings.qdrant_url)

        for collection_name in ["nexus_text", "nexus_visual"]:
            if client.collection_exists(collection_name):
                info = client.get_collection(collection_name)
                point_count = info.points_count
                if point_count and point_count > 0:
                    # Delete all points by scrolling through IDs
                    client.delete(
                        collection_name=collection_name,
                        points_selector=FilterSelector(filter=models.Filter(must=[])),
                    )
                    print(f"  {collection_name}: deleted {point_count} points")
                else:
                    print(f"  {collection_name}: already empty")
            else:
                print(f"  {collection_name}: doesn't exist (will be created on API start)")
        print("  Qdrant wiped\n")
    except Exception as exc:
        print(f"  Qdrant wipe failed: {exc}\n")


def wipe_neo4j(settings: Settings) -> None:
    """Delete all nodes and relationships from Neo4j."""
    print("=== Wiping Neo4j ===")
    try:
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
        with driver.session() as session:
            result = session.run("MATCH (n) DETACH DELETE n")
            summary = result.consume()
            print(
                f"  Deleted {summary.counters.nodes_deleted} nodes, {summary.counters.relationships_deleted} relationships"
            )
        driver.close()
        print("  Neo4j wiped\n")
    except Exception as exc:
        print(f"  Neo4j wipe failed: {exc}\n")


def wipe_minio(settings: Settings) -> None:
    """Clear all objects from the documents bucket in MinIO."""
    print("=== Wiping MinIO ===")
    try:
        import boto3
        from botocore.client import Config

        s3 = boto3.client(
            "s3",
            endpoint_url=f"http://{settings.minio_endpoint}",
            aws_access_key_id=settings.minio_access_key,
            aws_secret_access_key=settings.minio_secret_key,
            config=Config(signature_version="s3v4"),
        )
        bucket = settings.minio_bucket
        paginator = s3.get_paginator("list_objects_v2")
        count = 0
        for page in paginator.paginate(Bucket=bucket):
            objects = page.get("Contents", [])
            if objects:
                s3.delete_objects(
                    Bucket=bucket,
                    Delete={"Objects": [{"Key": o["Key"]} for o in objects]},
                )
                count += len(objects)
        print(f"  Deleted {count} objects from bucket '{bucket}'")
        print("  MinIO wiped\n")
    except Exception as exc:
        print(f"  MinIO wipe failed: {exc}\n")


def wipe_redis(settings: Settings) -> None:
    """Flush the Redis database (Celery broker, results, cache)."""
    print("=== Wiping Redis ===")
    try:
        import redis

        r = redis.from_url(settings.redis_url)
        r.flushdb()
        print("  FLUSHDB complete")
        print("  Redis wiped\n")
    except Exception as exc:
        print(f"  Redis wipe failed: {exc}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Wipe all NEXUS data stores")
    parser.add_argument(
        "--drop-db",
        action="store_true",
        help="Drop and recreate PostgreSQL public schema, then run alembic upgrade head",
    )
    args = parser.parse_args()

    settings = Settings()
    print("\nWiping all data stores...\n")
    wipe_postgres(settings, drop_db=args.drop_db)
    wipe_qdrant(settings)
    wipe_neo4j(settings)
    wipe_minio(settings)
    wipe_redis(settings)
    print("=== All stores wiped. Ready for re-ingest. ===\n")


if __name__ == "__main__":
    main()
