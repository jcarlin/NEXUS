#!/usr/bin/env python3
"""Build EFTA ground-truth dataset from corpus sample report.

Reads the corpus sample JSON (produced by sample_corpus.py), generates
question templates with real entity names and filenames, optionally runs
each question against the live API, and outputs a review file + final
ground-truth JSON.

Usage:
    # Generate questions from sample report (no API calls)
    python scripts/build_efta_ground_truth.py \
        --sample reports/efta_corpus_sample.json \
        --output evaluation/data/efta_ground_truth.json

    # Generate + run each question against API for expected-answer proposals
    python scripts/build_efta_ground_truth.py \
        --sample reports/efta_corpus_sample.json \
        --api-url http://34.169.203.200:8000 \
        --output evaluation/data/efta_ground_truth.json \
        --review reports/efta_gt_review.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

import httpx

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EPSTEIN_MATTER_ID = "00000000-0000-0000-0000-000000000002"
DEFAULT_API_URL = "http://34.169.203.200:8000"
DEFAULT_EMAIL = "admin@nexus-demo.com"
DEFAULT_PASSWORD = "nexus-demo-2026"


# ---------------------------------------------------------------------------
# Question templates
# ---------------------------------------------------------------------------

# Each template has placeholders that get filled from the corpus sample.
# {person_1}, {person_2}, etc. are replaced with actual entity names.
# {doc_filename} is replaced with an actual filename from the corpus.

EASY_TEMPLATES = [
    {
        "id": "efta-001",
        "template": "Who is {person_1} according to the documents?",
        "category": "factual",
        "difficulty": "easy",
        "tags": ["dense", "entity-lookup"],
        "needs": ["person_1"],
    },
    {
        "id": "efta-002",
        "template": "What role did {person_2} play in the Epstein investigation?",
        "category": "factual",
        "difficulty": "easy",
        "tags": ["dense", "graph"],
        "needs": ["person_2"],
    },
    {
        "id": "efta-003",
        "template": "What does the document '{doc_filename_1}' describe?",
        "category": "factual",
        "difficulty": "easy",
        "tags": ["dense", "doc-retrieval"],
        "needs": ["doc_filename_1"],
    },
    {
        "id": "efta-004",
        "template": "What is the Non-Prosecution Agreement (NPA) referenced in the documents?",
        "category": "factual",
        "difficulty": "easy",
        "tags": ["dense", "case-context"],
        "needs": [],
    },
    {
        "id": "efta-005",
        "template": "What locations are mentioned in connection with {person_1}?",
        "category": "factual",
        "difficulty": "easy",
        "tags": ["dense", "entity-lookup", "graph"],
        "needs": ["person_1"],
    },
    {
        "id": "efta-006",
        "template": "Who is {person_3} and what is their connection to the case?",
        "category": "factual",
        "difficulty": "easy",
        "tags": ["dense", "entity-lookup"],
        "needs": ["person_3"],
    },
    {
        "id": "efta-007",
        "template": "What does the document '{doc_filename_2}' describe?",
        "category": "factual",
        "difficulty": "easy",
        "tags": ["dense", "doc-retrieval"],
        "needs": ["doc_filename_2"],
    },
    {
        "id": "efta-008",
        "template": "What organizations are associated with {person_2}?",
        "category": "factual",
        "difficulty": "easy",
        "tags": ["dense", "graph", "entity-lookup"],
        "needs": ["person_2"],
    },
    {
        "id": "efta-009",
        "template": "What is the current status of cryptocurrency regulation in the United States?",
        "category": "factual",
        "difficulty": "easy",
        "tags": ["out-of-scope"],
        "needs": [],
        "expected_answer": "This question is outside the scope of the document corpus. The documents relate to the Epstein investigation and do not contain information about cryptocurrency regulation.",
        "expected_documents": [],
    },
    {
        "id": "efta-010",
        "template": "What patent disputes exist between entities mentioned in these documents?",
        "category": "factual",
        "difficulty": "easy",
        "tags": ["out-of-scope"],
        "needs": [],
        "expected_answer": "The document corpus does not contain information about patent disputes. The documents relate to the Epstein investigation.",
        "expected_documents": [],
    },
]

MEDIUM_TEMPLATES = [
    {
        "id": "efta-011",
        "template": "What connections exist between {person_1} and {person_2} according to the documents?",
        "category": "analytical",
        "difficulty": "medium",
        "tags": ["graph", "text-to-cypher", "dense"],
        "needs": ["person_1", "person_2"],
    },
    {
        "id": "efta-012",
        "template": "Describe the timeline of the Epstein investigation based on the documents.",
        "category": "timeline",
        "difficulty": "medium",
        "tags": ["temporal", "multi-doc", "dense"],
        "needs": [],
    },
    {
        "id": "efta-013",
        "template": "What organizations are mentioned in the FBI interview reports?",
        "category": "analytical",
        "difficulty": "medium",
        "tags": ["dense", "sparse", "entity-lookup"],
        "needs": [],
    },
    {
        "id": "efta-014",
        "template": "What did {person_4} state in their interview or deposition?",
        "category": "factual",
        "difficulty": "medium",
        "tags": ["dense", "reranker", "multi-query"],
        "needs": ["person_4"],
    },
    {
        "id": "efta-015",
        "template": "Which documents have the highest importance scores and what makes them significant?",
        "category": "analytical",
        "difficulty": "medium",
        "tags": ["hot-doc", "sentiment", "dense"],
        "needs": [],
    },
    {
        "id": "efta-016",
        "template": "What do the FBI FD-302 interview reports reveal about {person_1}?",
        "category": "analytical",
        "difficulty": "medium",
        "tags": ["sparse", "dense", "multi-query"],
        "needs": ["person_1"],
    },
    {
        "id": "efta-017",
        "template": "What financial information is documented in the corpus?",
        "category": "analytical",
        "difficulty": "medium",
        "tags": ["dense", "entity-lookup", "text-to-sql"],
        "needs": [],
    },
    {
        "id": "efta-018",
        "template": "How many documents of each type are in the corpus?",
        "category": "factual",
        "difficulty": "medium",
        "tags": ["text-to-sql"],
        "needs": [],
    },
    {
        "id": "efta-019",
        "template": "What role did {location_1} play in the events described in the documents?",
        "category": "analytical",
        "difficulty": "medium",
        "tags": ["dense", "graph", "multi-query"],
        "needs": ["location_1"],
    },
    {
        "id": "efta-020",
        "template": "What law enforcement agencies are mentioned and what were their roles?",
        "category": "analytical",
        "difficulty": "medium",
        "tags": ["dense", "entity-lookup", "graph"],
        "needs": [],
    },
]

HARD_TEMPLATES = [
    {
        "id": "efta-021",
        "template": "Map the network of associates connected to {person_1} through intermediaries in the documents.",
        "category": "exploratory",
        "difficulty": "hard",
        "tags": ["text-to-cypher", "centrality", "graph", "multi-hop"],
        "needs": ["person_1"],
    },
    {
        "id": "efta-022",
        "template": "What contradictions or inconsistencies exist between different witnesses' accounts in the depositions?",
        "category": "analytical",
        "difficulty": "hard",
        "tags": ["decomposition", "multi-hop", "reranker"],
        "needs": [],
    },
    {
        "id": "efta-023",
        "template": "What patterns of concealment or obstruction are documented across the corpus?",
        "category": "exploratory",
        "difficulty": "hard",
        "tags": ["sentiment", "hyde", "dense", "context-gap"],
        "needs": [],
    },
    {
        "id": "efta-024",
        "template": "Trace the flow of information between law enforcement agencies as documented in these files.",
        "category": "analytical",
        "difficulty": "hard",
        "tags": ["decomposition", "temporal", "graph", "multi-hop"],
        "needs": [],
    },
    {
        "id": "efta-025",
        "template": "What context gaps or missing information were identified in the documents?",
        "category": "exploratory",
        "difficulty": "hard",
        "tags": ["context-gap", "dense"],
        "needs": [],
    },
    {
        "id": "efta-026",
        "template": "Who are the most connected individuals in the knowledge graph and what are their roles?",
        "category": "exploratory",
        "difficulty": "hard",
        "tags": ["centrality", "entity-lookup", "graph"],
        "needs": [],
    },
    {
        "id": "efta-027",
        "template": "What is the relationship between {person_1}, {person_3}, and {location_1} based on the documents?",
        "category": "analytical",
        "difficulty": "hard",
        "tags": ["multi-query", "graph", "temporal", "decomposition"],
        "needs": ["person_1", "person_3", "location_1"],
    },
    {
        "id": "efta-028",
        "template": "Create a comprehensive timeline of all legal proceedings involving {person_1} documented in the corpus.",
        "category": "timeline",
        "difficulty": "hard",
        "tags": ["temporal", "multi-query", "adaptive-depth", "multi-doc"],
        "needs": ["person_1"],
    },
    {
        "id": "efta-029",
        "template": "What role did specific locations ({location_1}, {location_2}) play across the investigation?",
        "category": "exploratory",
        "difficulty": "hard",
        "tags": ["multi-query", "graph", "temporal"],
        "needs": ["location_1", "location_2"],
    },
    {
        "id": "efta-030",
        "template": "Identify all individuals who are mentioned in connection with both {org_1} and {location_1}.",
        "category": "analytical",
        "difficulty": "hard",
        "tags": ["text-to-cypher", "graph", "entity-lookup"],
        "needs": ["org_1", "location_1"],
    },
]

ALL_TEMPLATES = EASY_TEMPLATES + MEDIUM_TEMPLATES + HARD_TEMPLATES


# ---------------------------------------------------------------------------
# Placeholder resolution
# ---------------------------------------------------------------------------


def resolve_placeholders(sample: dict) -> dict[str, str]:
    """Extract real entity names and filenames from the corpus sample report."""
    placeholders: dict[str, str] = {}

    # People (sorted by mention_count desc)
    people = sample.get("top_entities", {}).get("person", [])
    for i, p in enumerate(people[:10], 1):
        placeholders[f"person_{i}"] = p.get("name", f"Person_{i}")

    # Organizations
    orgs = sample.get("top_entities", {}).get("organization", [])
    for i, o in enumerate(orgs[:5], 1):
        placeholders[f"org_{i}"] = o.get("name", f"Org_{i}")

    # Locations
    locations = sample.get("top_entities", {}).get("location", [])
    for i, loc in enumerate(locations[:5], 1):
        placeholders[f"location_{i}"] = loc.get("name", f"Location_{i}")

    # Document filenames (pick from different types for variety)
    doc_idx = 1
    for dtype, docs in sample.get("documents_by_type", {}).items():
        for d in docs[:2]:
            placeholders[f"doc_filename_{doc_idx}"] = d.get("filename", f"doc_{doc_idx}.pdf")
            doc_idx += 1
            if doc_idx > 10:
                break
        if doc_idx > 10:
            break

    return placeholders


def build_questions(templates: list[dict], placeholders: dict[str, str]) -> list[dict]:
    """Fill templates with real entity names and build GroundTruthItem dicts."""
    items = []
    for tmpl in templates:
        # Check if all needed placeholders are available
        missing = [k for k in tmpl.get("needs", []) if k not in placeholders]
        if missing:
            print(f"  Skipping {tmpl['id']}: missing placeholders {missing}")
            continue

        # Fill template
        question = tmpl["template"]
        for key, value in placeholders.items():
            question = question.replace(f"{{{key}}}", value)

        item = {
            "id": tmpl["id"],
            "question": question,
            "expected_answer": tmpl.get("expected_answer", ""),
            "category": tmpl["category"],
            "difficulty": tmpl["difficulty"],
            "expected_documents": tmpl.get("expected_documents", []),
            "matter_id": EPSTEIN_MATTER_ID,
            "tags": tmpl["tags"],
        }
        items.append(item)

    return items


# ---------------------------------------------------------------------------
# API query runner (optional — fills in expected answers from live responses)
# ---------------------------------------------------------------------------


async def authenticate(client: httpx.AsyncClient, api_url: str, email: str, password: str) -> str:
    """Login with credential fallback."""
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


async def run_query(
    client: httpx.AsyncClient,
    api_url: str,
    headers: dict,
    question: str,
) -> dict:
    """Run a query against the live API and return response + sources."""
    resp = await client.post(
        f"{api_url}/api/v1/query",
        headers=headers,
        json={"query": question, "matter_id": EPSTEIN_MATTER_ID},
        timeout=180.0,
    )
    if resp.status_code != 200:
        return {"error": resp.text[:500], "status": resp.status_code}
    return resp.json()


async def enrich_with_api_responses(
    items: list[dict],
    api_url: str,
    email: str,
    password: str,
) -> list[dict]:
    """Run each question against the API and attach response data for review."""
    review_items = []

    async with httpx.AsyncClient(timeout=60.0) as client:
        token = await authenticate(client, api_url, email, password)
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Matter-ID": EPSTEIN_MATTER_ID,
        }

        for i, item in enumerate(items):
            print(f"  [{i + 1}/{len(items)}] Querying: {item['question'][:80]}...")

            # Skip out-of-scope questions
            if "out-of-scope" in item.get("tags", []):
                review_items.append({**item, "api_response": None, "api_sources": []})
                continue

            try:
                result = await run_query(client, api_url, headers, item["question"])
                response_text = result.get("response", "")
                sources = result.get("source_documents", [])
                source_filenames = [s.get("filename", "") for s in sources]

                review_items.append(
                    {
                        **item,
                        "api_response": response_text[:2000],
                        "api_sources": source_filenames[:15],
                        "api_cited_claims": len(result.get("cited_claims", [])),
                    }
                )
            except Exception as exc:
                print(f"    Error: {exc}")
                review_items.append({**item, "api_response": f"ERROR: {exc}", "api_sources": []})

    return review_items


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def write_ground_truth(items: list[dict], output_path: Path) -> None:
    """Write the final ground-truth JSON in v2.0 format."""
    # Strip API response fields — those are only for the review file
    clean_items = []
    for item in items:
        clean = {k: v for k, v in item.items() if not k.startswith("api_")}
        clean_items.append(clean)

    dataset = {"version": "2.0", "ground_truth": clean_items}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(dataset, indent=2))
    print(f"\nGround-truth dataset written to {output_path} ({len(clean_items)} items)")


def write_review_file(items: list[dict], review_path: Path) -> None:
    """Write the review JSON with API responses for human inspection."""
    review_path.parent.mkdir(parents=True, exist_ok=True)
    review_path.write_text(json.dumps(items, indent=2))
    print(f"Review file written to {review_path} ({len(items)} items)")
    print("\n  Review the file, then:")
    print("  1. Edit expected_answer for each item (use api_response as starting point)")
    print("  2. Edit expected_documents (use api_sources as starting point)")
    print("  3. Delete api_response, api_sources, api_cited_claims fields")
    print("  4. Save as evaluation/data/efta_ground_truth.json")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build EFTA ground-truth dataset from corpus sample report.",
    )
    parser.add_argument(
        "--sample",
        required=True,
        help="Path to corpus sample JSON (from sample_corpus.py)",
    )
    parser.add_argument(
        "--output",
        default="evaluation/data/efta_ground_truth.json",
        help="Output ground-truth JSON path",
    )
    parser.add_argument(
        "--api-url",
        default=None,
        help="NEXUS API URL (if set, runs each question for answer proposals)",
    )
    parser.add_argument("--email", default=DEFAULT_EMAIL, help="Login email")
    parser.add_argument("--password", default=DEFAULT_PASSWORD, help="Login password")
    parser.add_argument(
        "--review",
        default=None,
        help="Path for review JSON with API responses (requires --api-url)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    start = time.perf_counter()

    # Load corpus sample
    sample_path = Path(args.sample)
    if not sample_path.exists():
        print(f"Error: sample file not found: {sample_path}", file=sys.stderr)
        print("Run sample_corpus.py first.", file=sys.stderr)
        return 1

    sample = json.loads(sample_path.read_text())
    print(f"Loaded corpus sample from {sample_path}")

    # Resolve placeholders
    placeholders = resolve_placeholders(sample)
    print(f"\nResolved {len(placeholders)} placeholders:")
    for key, value in sorted(placeholders.items()):
        print(f"  {key}: {value}")

    # Build questions
    print(f"\nBuilding questions from {len(ALL_TEMPLATES)} templates...")
    items = build_questions(ALL_TEMPLATES, placeholders)
    print(f"  Generated {len(items)} questions")

    # Optionally enrich with API responses
    if args.api_url:
        print(f"\nRunning queries against {args.api_url}...")
        items = asyncio.run(enrich_with_api_responses(items, args.api_url, args.email, args.password))

        # Write review file
        review_path = Path(args.review or "reports/efta_gt_review.json")
        write_review_file(items, review_path)

    # Write ground-truth JSON
    output_path = Path(args.output)
    write_ground_truth(items, output_path)

    elapsed = time.perf_counter() - start
    print(f"\nCompleted in {elapsed:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
