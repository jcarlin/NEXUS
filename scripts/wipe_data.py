"""Wipe all NEXUS data stores for a clean re-ingest.

Clears: PostgreSQL (data tables), Qdrant (all points), Neo4j (all nodes), MinIO (document objects).
Preserves: users, case_matters, user_case_matters, audit_log, ai_audit_log, datasets table structure.

Usage:
    python scripts/wipe_data.py
"""

from __future__ import annotations

import os
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


def wipe_postgres(settings: Settings) -> None:
    """Delete data tables in dependency order, preserving users/matters/audit."""
    print("=== Wiping PostgreSQL ===")
    engine = create_engine(settings.postgres_url_sync, pool_pre_ping=True)

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
        "chunks",
        "jobs",
        "documents",
    ]

    with engine.connect() as conn:
        # Use TRUNCATE CASCADE for tables with FK dependencies
        try:
            conn.execute(text("TRUNCATE TABLE " + ", ".join(tables_to_clear) + " CASCADE"))
            print(f"  Truncated {len(tables_to_clear)} tables (CASCADE)")
        except Exception as exc:
            print(f"  TRUNCATE failed ({exc}), falling back to DELETE...")
            for table in tables_to_clear:
                try:
                    result = conn.execute(text(f"DELETE FROM {table}"))  # noqa: S608
                    print(f"  {table}: {result.rowcount} rows deleted")
                except Exception as exc2:
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
    """Delete and recreate the Qdrant collection."""
    print("=== Wiping Qdrant ===")
    try:
        from qdrant_client import QdrantClient

        client = QdrantClient(url=settings.qdrant_url)
        collection_name = "nexus_text"

        if client.collection_exists(collection_name):
            client.delete_collection(collection_name)
            print(f"  Deleted collection: {collection_name}")
        else:
            print(f"  Collection {collection_name} doesn't exist")
        print("  Qdrant wiped (collection will auto-recreate on next ingest)\n")
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
        from minio import Minio

        client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_use_ssl,
        )
        bucket = settings.minio_bucket
        if client.bucket_exists(bucket):
            objects = list(client.list_objects(bucket, recursive=True))
            for obj in objects:
                client.remove_object(bucket, obj.object_name)
            print(f"  Deleted {len(objects)} objects from bucket '{bucket}'")
        else:
            print(f"  Bucket '{bucket}' doesn't exist")
        print("  MinIO wiped\n")
    except Exception as exc:
        print(f"  MinIO wipe failed: {exc}\n")


def main() -> None:
    settings = Settings()
    print("\nWiping all data stores...\n")
    wipe_postgres(settings)
    wipe_qdrant(settings)
    wipe_neo4j(settings)
    wipe_minio(settings)
    print("=== All stores wiped. Ready for re-ingest. ===\n")


if __name__ == "__main__":
    main()
