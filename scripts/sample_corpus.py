#!/usr/bin/env python3
"""Sample the ingested EFTA corpus to discover entities, documents, and relationships.

Queries the live NEXUS API and produces a structured JSON report that informs
ground-truth dataset construction for retrieval evaluation.

Usage:
    python scripts/sample_corpus.py \
        --api-url http://34.169.203.200:8000 \
        --matter-id 00000000-0000-0000-0000-000000000002 \
        --output reports/efta_corpus_sample.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EPSTEIN_MATTER_ID = "00000000-0000-0000-0000-000000000002"
DEFAULT_API_URL = "http://34.169.203.200:8000"
DEFAULT_EMAIL = "admin@nexus-demo.com"
DEFAULT_PASSWORD = "nexus-demo-2026"

DOCUMENT_TYPES = [
    "deposition",
    "correspondence",
    "report",
    "legal_filing",
    "financial",
    "email",
    "image",
    "other",
]

ENTITY_TYPES = [
    "person",
    "organization",
    "location",
    "date",
    "case_number",
    "court",
    "monetary_amount",
    "vehicle",
    "flight_number",
    "phone_number",
    "email_address",
    "address",
]


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


async def authenticate(client: httpx.AsyncClient, api_url: str, email: str, password: str) -> str:
    """Login and return JWT access token.  Tries provided creds first, then fallbacks."""
    url = f"{api_url}/api/v1/auth/login"
    cred_pairs = [
        (email, password),
        ("admin@example.com", "password123"),
        ("admin@nexus-demo.com", "nexus-demo-2026"),
    ]
    for e, p in cred_pairs:
        resp = await client.post(url, json={"email": e, "password": p})
        if resp.status_code == 200:
            return resp.json()["access_token"]
    resp.raise_for_status()
    return ""  # unreachable


# ---------------------------------------------------------------------------
# Sampling functions
# ---------------------------------------------------------------------------


async def get_corpus_stats(client: httpx.AsyncClient, api_url: str, headers: dict) -> dict:
    """Fetch aggregate corpus statistics."""
    resp = await client.get(f"{api_url}/api/v1/documents/stats", headers=headers)
    resp.raise_for_status()
    return resp.json()


async def get_document_health(client: httpx.AsyncClient, api_url: str, headers: dict) -> dict:
    """Fetch vector index health summary."""
    resp = await client.get(f"{api_url}/api/v1/documents/health", headers=headers)
    if resp.status_code == 200:
        data = resp.json()
        return {
            "total": data.get("total", 0),
            "healthy": data.get("healthy", 0),
            "missing": data.get("missing", 0),
            "partial": data.get("partial", 0),
        }
    return {"error": resp.text[:500]}


async def sample_documents_by_type(client: httpx.AsyncClient, api_url: str, headers: dict) -> dict[str, list[dict]]:
    """Fetch a few sample documents for each document type."""
    result: dict[str, list[dict]] = {}
    for doc_type in DOCUMENT_TYPES:
        resp = await client.get(
            f"{api_url}/api/v1/documents",
            headers=headers,
            params={"document_type": doc_type, "limit": 5, "offset": 0},
        )
        if resp.status_code == 200:
            data = resp.json()
            items = data.get("items", [])
            result[doc_type] = [
                {
                    "id": d["id"],
                    "filename": d["filename"],
                    "page_count": d.get("page_count", 0),
                    "chunk_count": d.get("chunk_count", 0),
                    "entity_count": d.get("entity_count", 0),
                    "hot_doc_score": d.get("hot_doc_score"),
                    "summary": d.get("summary"),
                    "type": d.get("type"),
                }
                for d in items
            ]
            if data.get("total", 0) > 0:
                print(f"  {doc_type}: {data['total']} documents (sampled {len(items)})")
        else:
            result[doc_type] = []
    return result


async def get_hot_documents(client: httpx.AsyncClient, api_url: str, headers: dict) -> list[dict]:
    """Fetch documents with highest hot_doc_score."""
    resp = await client.get(
        f"{api_url}/api/v1/documents",
        headers=headers,
        params={"hot_doc_score_min": 0.3, "limit": 20, "offset": 0},
    )
    if resp.status_code != 200:
        return []
    items = resp.json().get("items", [])
    return [
        {
            "id": d["id"],
            "filename": d["filename"],
            "hot_doc_score": d.get("hot_doc_score"),
            "summary": d.get("summary"),
            "page_count": d.get("page_count", 0),
            "type": d.get("type"),
        }
        for d in items
    ]


async def get_document_detail(client: httpx.AsyncClient, api_url: str, headers: dict, doc_id: str) -> dict | None:
    """Fetch full detail for a single document (includes sentiment, context gaps)."""
    resp = await client.get(f"{api_url}/api/v1/documents/{doc_id}", headers=headers)
    if resp.status_code != 200:
        return None
    return resp.json()


async def get_top_entities(client: httpx.AsyncClient, api_url: str, headers: dict) -> dict[str, list[dict]]:
    """Fetch top entities by type, sorted by mention count."""
    result: dict[str, list[dict]] = {}
    for etype in ENTITY_TYPES:
        resp = await client.get(
            f"{api_url}/api/v1/entities",
            headers=headers,
            params={"entity_type": etype, "limit": 30, "offset": 0},
        )
        if resp.status_code == 200:
            data = resp.json()
            items = data.get("items", [])
            result[etype] = items
            total = data.get("total", 0)
            if total > 0:
                print(f"  {etype}: {total} entities (sampled {len(items)})")
        else:
            result[etype] = []
    return result


async def get_entity_connections(
    client: httpx.AsyncClient, api_url: str, headers: dict, entity_names: list[str]
) -> list[dict]:
    """Fetch connections for top entities to build a relationship map."""
    clusters = []
    for name in entity_names[:10]:  # Top 10 only
        resp = await client.get(
            f"{api_url}/api/v1/entities/connections",
            headers=headers,
            params={"name": name, "entity_only": "true", "limit": 20},
        )
        if resp.status_code == 200:
            data = resp.json()
            connections = data.get("connections", [])
            clusters.append(
                {
                    "center": name,
                    "entity": data.get("entity"),
                    "connections": connections[:20],
                    "total_connections": len(connections),
                }
            )
    return clusters


async def get_graph_stats(client: httpx.AsyncClient, api_url: str, headers: dict) -> dict:
    """Fetch Neo4j graph node/edge counts."""
    resp = await client.get(f"{api_url}/api/v1/graph/stats", headers=headers)
    if resp.status_code == 200:
        return resp.json()
    return {"error": resp.text[:500]}


async def get_communication_matrix(client: httpx.AsyncClient, api_url: str, headers: dict) -> dict:
    """Fetch pre-computed communication pairs."""
    resp = await client.get(f"{api_url}/api/v1/analytics/communication-matrix", headers=headers)
    if resp.status_code == 200:
        return resp.json()
    return {"error": resp.text[:500], "status": resp.status_code}


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def print_summary(report: dict) -> None:
    """Print a human-readable summary of the corpus sample."""
    stats = report.get("corpus_stats", {})
    health = report.get("health", {})
    graph = report.get("graph_stats", {})

    print("\n" + "=" * 70)
    print("EFTA CORPUS SAMPLE REPORT")
    print("=" * 70)

    print("\n--- Corpus Stats ---")
    print(f"  Documents: {stats.get('doc_count', '?')}")
    print(f"  Total pages: {stats.get('total_pages', '?')}")
    size_mb = stats.get("total_size_bytes", 0) / (1024 * 1024)
    print(f"  Total size: {size_mb:.1f} MB")

    print("\n--- Vector Index Health ---")
    print(f"  Healthy: {health.get('healthy', '?')}/{health.get('total', '?')}")
    print(f"  Missing: {health.get('missing', '?')}")
    print(f"  Partial: {health.get('partial', '?')}")

    print("\n--- Graph Stats ---")
    if "error" not in graph:
        print(f"  Total nodes: {graph.get('total_nodes', '?')}")
        print(f"  Total edges: {graph.get('total_edges', '?')}")
        node_counts = graph.get("node_counts", {})
        for ntype, count in sorted(node_counts.items(), key=lambda x: -x[1])[:10]:
            print(f"    {ntype}: {count}")

    # Top entities
    entities = report.get("top_entities", {})
    for etype in ["person", "organization", "location"]:
        items = entities.get(etype, [])
        if items:
            print(f"\n--- Top {etype.title()}s ---")
            for e in items[:10]:
                name = e.get("name", "?")
                mentions = e.get("mention_count", e.get("mentions", "?"))
                print(f"  {name} ({mentions} mentions)")

    # Hot documents
    hot_docs = report.get("hot_documents", [])
    if hot_docs:
        print(f"\n--- Hot Documents (top {len(hot_docs)}) ---")
        for d in hot_docs[:10]:
            score = d.get("hot_doc_score", 0) or 0
            print(f"  [{score:.2f}] {d['filename']}")
            if d.get("summary"):
                print(f"         {d['summary'][:120]}...")

    # Entity clusters
    clusters = report.get("entity_clusters", [])
    if clusters:
        print(f"\n--- Entity Connection Clusters (top {len(clusters)}) ---")
        for c in clusters[:5]:
            conns = c.get("connections", [])
            print(f"  {c['center']} → {len(conns)} connections")
            for conn in conns[:5]:
                target = conn.get("target", conn.get("name", "?"))
                rel = conn.get("relationship", conn.get("type", "?"))
                print(f"    → {target} ({rel})")

    # Document type distribution
    docs_by_type = report.get("documents_by_type", {})
    if docs_by_type:
        print("\n--- Sample Documents by Type ---")
        for dtype, docs in docs_by_type.items():
            if docs:
                print(f"\n  [{dtype}]")
                for d in docs[:3]:
                    print(f"    {d['filename']} ({d.get('page_count', 0)} pages, {d.get('chunk_count', 0)} chunks)")
                    if d.get("summary"):
                        print(f"      {d['summary'][:120]}")

    # Communication matrix
    comms = report.get("communication_matrix", {})
    if "pairs" in comms:
        pairs = comms["pairs"]
        print(f"\n--- Communication Pairs ({len(pairs)} total) ---")
        for p in pairs[:10]:
            print(f"  {p.get('sender', '?')} → {p.get('recipient', '?')}: {p.get('message_count', '?')} messages")

    print("\n" + "=" * 70)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def run(args: argparse.Namespace) -> dict:
    """Execute all sampling queries and build the report."""
    report: dict = {
        "generated_at": datetime.now(UTC).isoformat(),
        "api_url": args.api_url,
        "matter_id": args.matter_id,
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        # Authenticate
        print("[1/8] Authenticating...")
        token = await authenticate(client, args.api_url, args.email, args.password)
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Matter-ID": args.matter_id,
        }
        print(f"  Authenticated as {args.email}")

        # Corpus stats
        print("\n[2/8] Fetching corpus stats...")
        report["corpus_stats"] = await get_corpus_stats(client, args.api_url, headers)
        print(
            f"  {report['corpus_stats'].get('doc_count', '?')} documents, "
            f"{report['corpus_stats'].get('total_pages', '?')} pages"
        )

        # Health check
        print("\n[3/8] Checking vector index health...")
        report["health"] = await get_document_health(client, args.api_url, headers)
        h = report["health"]
        if "error" not in h:
            print(
                f"  Healthy: {h.get('healthy')}/{h.get('total')}, "
                f"Missing: {h.get('missing')}, Partial: {h.get('partial')}"
            )

        # Documents by type
        print("\n[4/8] Sampling documents by type...")
        report["documents_by_type"] = await sample_documents_by_type(client, args.api_url, headers)

        # Hot documents
        print("\n[5/8] Fetching hot documents...")
        report["hot_documents"] = await get_hot_documents(client, args.api_url, headers)
        print(f"  Found {len(report['hot_documents'])} hot documents")

        # Fetch detail for top 5 hot docs (sentiment, context gaps)
        hot_details = []
        for hd in report["hot_documents"][:5]:
            detail = await get_document_detail(client, args.api_url, headers, hd["id"])
            if detail:
                hot_details.append(
                    {
                        "filename": detail.get("filename"),
                        "hot_doc_score": detail.get("hot_doc_score"),
                        "sentiment_pressure": detail.get("sentiment_pressure"),
                        "sentiment_concealment": detail.get("sentiment_concealment"),
                        "sentiment_intent": detail.get("sentiment_intent"),
                        "context_gap_score": detail.get("context_gap_score"),
                        "context_gaps": detail.get("context_gaps", []),
                        "summary": detail.get("summary"),
                    }
                )
        report["hot_document_details"] = hot_details

        # Entities
        print("\n[6/8] Fetching top entities...")
        report["top_entities"] = await get_top_entities(client, args.api_url, headers)

        # Entity connections for top people
        people = report["top_entities"].get("person", [])
        top_people_names = [p.get("name", "") for p in people[:10] if p.get("name")]
        if top_people_names:
            print(f"\n  Fetching connections for top {len(top_people_names)} people...")
            report["entity_clusters"] = await get_entity_connections(client, args.api_url, headers, top_people_names)
        else:
            report["entity_clusters"] = []

        # Graph stats
        print("\n[7/8] Fetching graph stats...")
        report["graph_stats"] = await get_graph_stats(client, args.api_url, headers)

        # Communication matrix
        print("\n[8/8] Fetching communication matrix...")
        report["communication_matrix"] = await get_communication_matrix(client, args.api_url, headers)

    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sample the EFTA corpus for retrieval evaluation ground-truth construction.",
    )
    parser.add_argument("--api-url", default=DEFAULT_API_URL, help="NEXUS API base URL")
    parser.add_argument("--matter-id", default=EPSTEIN_MATTER_ID, help="Matter ID to scope queries")
    parser.add_argument("--email", default=DEFAULT_EMAIL, help="Login email")
    parser.add_argument("--password", default=DEFAULT_PASSWORD, help="Login password")
    parser.add_argument("--output", default="reports/efta_corpus_sample.json", help="Output JSON path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    start = time.perf_counter()

    try:
        report = asyncio.run(run(args))
    except httpx.HTTPStatusError as exc:
        print(f"\nHTTP error: {exc.response.status_code} {exc.response.text[:500]}", file=sys.stderr)
        return 1
    except httpx.ConnectError as exc:
        print(f"\nConnection failed: {exc}", file=sys.stderr)
        print(f"  Is the NEXUS API running at {args.api_url}?", file=sys.stderr)
        return 1

    elapsed = time.perf_counter() - start
    report["elapsed_seconds"] = round(elapsed, 1)

    # Write JSON
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, default=str))
    print(f"\nJSON report written to {output_path}")

    # Print summary
    print_summary(report)
    print(f"\nCompleted in {elapsed:.1f}s")

    return 0


if __name__ == "__main__":
    sys.exit(main())
