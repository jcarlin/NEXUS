#!/usr/bin/env python3
"""Diagnose NEXUS query pipeline performance.

Authenticates against the live API, runs health checks, sends an SSE query,
instruments each stage, and prints a diagnostic report.

Usage::

    # Basic diagnosis
    python scripts/diagnose_query.py \
        --api-url http://localhost:8000/api/v1 \
        --email admin@example.com \
        --password changeme \
        --matter-id <uuid> \
        --query "Who are the key parties?"

    # Verbose mode (print raw SSE events)
    python scripts/diagnose_query.py \
        --api-url http://localhost:8000/api/v1 \
        --email admin@example.com \
        --password changeme \
        --matter-id <uuid> \
        --verbose

    # Dry run (CI — validates arg parsing, exits 0)
    python scripts/diagnose_query.py --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Diagnose NEXUS query pipeline")
    parser.add_argument("--api-url", type=str, default="http://localhost:8000/api/v1")
    parser.add_argument("--email", type=str, default="admin@example.com")
    parser.add_argument("--password", type=str, default="changeme")
    parser.add_argument("--matter-id", type=str, default=None)
    parser.add_argument("--query", type=str, default="Who are the key parties in this matter?")
    parser.add_argument("--verbose", action="store_true", help="Print raw SSE events")
    parser.add_argument("--dry-run", action="store_true", help="Validate args and exit 0 (CI)")
    parser.add_argument("--compare", action="store_true", help="Note how to compare agentic vs v1")
    return parser.parse_args()


async def authenticate(client, api_url: str, email: str, password: str) -> str:
    """Login and return JWT access token."""
    resp = await client.post(
        f"{api_url}/auth/login",
        json={"email": email, "password": password},
    )
    resp.raise_for_status()
    token = resp.json()["access_token"]
    return token


async def check_health(client, api_url: str, headers: dict) -> dict:
    """Run basic + deep health checks and return results."""
    results = {}

    # Basic health
    try:
        start = time.perf_counter()
        resp = await client.get(f"{api_url}/health", headers=headers)
        elapsed = time.perf_counter() - start
        body = resp.json() if resp.status_code == 200 else {"error": resp.text[:500]}
        results["basic"] = {
            "status_code": resp.status_code,
            "latency_ms": round(elapsed * 1000),
            "body": body,
        }
    except Exception as e:
        results["basic"] = {
            "status_code": 0,
            "latency_ms": 0,
            "body": {"error": f"{type(e).__name__}: {e}"},
        }

    # Deep health (LLM + embedding + Qdrant stats)
    try:
        start = time.perf_counter()
        resp = await client.get(f"{api_url}/health/deep", headers=headers)
        elapsed = time.perf_counter() - start
        body = resp.json() if resp.status_code == 200 else {"error": resp.text[:500]}
        results["deep"] = {
            "status_code": resp.status_code,
            "latency_ms": round(elapsed * 1000),
            "body": body,
        }
    except Exception as e:
        results["deep"] = {
            "status_code": 0,
            "latency_ms": 0,
            "body": {"error": f"{type(e).__name__}: {e}"},
        }

    return results


async def run_query_stream(client, api_url: str, headers: dict, matter_id: str, query: str, verbose: bool) -> dict:
    """Send a query via SSE and instrument each stage."""
    import httpx

    stages: list[dict] = []
    tokens: list[str] = []
    sources_count = 0
    done_data: dict = {}
    tool_calls_seen = 0
    query_start = time.perf_counter()
    last_stage_time = query_start

    async with httpx.AsyncClient(timeout=httpx.Timeout(300.0)) as stream_client:
        async with stream_client.stream(
            "POST",
            f"{api_url}/query/stream",
            json={"query": query, "matter_id": matter_id},
            headers={**headers, "X-Matter-ID": matter_id},
        ) as resp:
            if resp.status_code != 200:
                body = await resp.aread()
                return {"error": f"HTTP {resp.status_code}: {body.decode()[:500]}"}

            current_event = ""
            current_data = ""

            async for line in resp.aiter_lines():
                if line.startswith("event:"):
                    current_event = line[6:].strip()
                    continue
                if line.startswith("data:"):
                    current_data = line[5:].strip()
                elif line == "" and current_event and current_data:
                    # Process complete SSE event
                    now = time.perf_counter()

                    if verbose:
                        print(f"  SSE [{current_event}]: {current_data[:200]}")

                    try:
                        data = json.loads(current_data)
                    except json.JSONDecodeError:
                        data = {"raw": current_data}

                    if current_event == "status":
                        stage_name = data.get("stage", "unknown")
                        stages.append(
                            {
                                "stage": stage_name,
                                "entered_at_ms": round((now - query_start) * 1000),
                                "since_last_ms": round((now - last_stage_time) * 1000),
                            }
                        )
                        last_stage_time = now

                    elif current_event == "token":
                        text_val = data.get("text", "")
                        tokens.append(text_val)

                    elif current_event == "sources":
                        docs = data.get("documents", [])
                        sources_count = len(docs)

                    elif current_event == "done":
                        done_data = data

                    current_event = ""
                    current_data = ""

    total_ms = round((time.perf_counter() - query_start) * 1000)
    response_text = "".join(tokens)

    return {
        "total_ms": total_ms,
        "stages": stages,
        "token_count": len(tokens),
        "response_length": len(response_text),
        "response_preview": response_text[:200],
        "sources_count": sources_count,
        "done_data": done_data,
        "tool_calls_seen": tool_calls_seen,
    }


def print_report(health: dict, query_result: dict, args: argparse.Namespace) -> None:
    """Print a formatted diagnostic report."""
    print("\n" + "=" * 70)
    print("NEXUS QUERY PIPELINE DIAGNOSTIC REPORT")
    print("=" * 70)

    # Health summary
    print("\n--- Health Checks ---")
    basic = health["basic"]
    print(f"  Basic health: HTTP {basic['status_code']} ({basic['latency_ms']}ms)")
    for svc, status in basic["body"].get("services", {}).items():
        icon = "OK" if status == "ok" else "FAIL"
        print(f"    {svc}: {icon}")

    deep = health["deep"]
    print(f"\n  Deep health: HTTP {deep['status_code']} ({deep['latency_ms']}ms)")
    for svc, info in deep["body"].get("services", {}).items():
        if isinstance(info, dict):
            status = info.get("status", "unknown")
            icon = "OK" if status == "ok" else "FAIL"
            latency = info.get("latency_ms", "")
            extra = f" ({latency}ms)" if latency else ""
            print(f"    {svc}: {icon}{extra}")
            if svc == "embedding" and status == "ok":
                dims = info.get("dimensions", "?")
                expected = info.get("expected_dimensions", "?")
                match = "MATCH" if dims == expected else f"MISMATCH (got {dims}, expected {expected})"
                print(f"      dimensions: {match}")
            if svc == "qdrant_nexus_text" and status == "ok":
                print(f"      points: {info.get('points_count', '?')}, vectors: {info.get('vectors_count', '?')}")

    # Query result
    print("\n--- Query Performance ---")
    if "error" in query_result:
        print(f"  ERROR: {query_result['error']}")
        return

    print(f'  Query: "{args.query}"')
    print(f"  Total time: {query_result['total_ms']}ms ({query_result['total_ms'] / 1000:.1f}s)")
    print(f"  Tokens received: {query_result['token_count']}")
    print(f"  Sources found: {query_result['sources_count']}")
    print(f"  Response length: {query_result['response_length']} chars")

    # Stage timing waterfall
    stages = query_result.get("stages", [])
    if stages:
        print("\n  Stage Waterfall:")
        for i, s in enumerate(stages):
            bar_len = min(s["since_last_ms"] // 100, 40)
            bar = "#" * bar_len if bar_len > 0 else "."
            print(f"    {s['stage']:<25s} +{s['since_last_ms']:>6d}ms  @{s['entered_at_ms']:>6d}ms  {bar}")

    # Bottleneck identification
    print("\n--- Bottleneck Analysis ---")
    if stages:
        slowest = max(stages, key=lambda s: s["since_last_ms"])
        print(f"  Slowest stage: {slowest['stage']} ({slowest['since_last_ms']}ms)")

        if slowest["stage"] == "verifying_citations" and slowest["since_last_ms"] > 10000:
            print("  >> Citation verification is the bottleneck.")
            print("     Consider: ENABLE_CITATION_VERIFICATION=false or reduce MAX_CLAIMS_TO_VERIFY")
        elif slowest["stage"] == "investigating" and slowest["since_last_ms"] > 20000:
            print("  >> Agent investigation loop is the bottleneck.")
            print("     Consider: reducing AGENTIC_RECURSION_LIMIT_STANDARD or checking tool latency")

    if query_result["token_count"] == 0:
        print("  WARNING: No tokens received — the agent may not be generating a response.")
        print("     Check: build_system_prompt returns [SystemMessage] + messages (commit fd33427)")
    if query_result["sources_count"] == 0:
        print("  WARNING: No sources found — retrieval may be failing.")
        print("     Check: Qdrant has indexed documents for this matter, embedding service is running")

    # Response preview
    print("\n--- Response Preview ---")
    preview = query_result.get("response_preview", "(empty)")
    print(f"  {preview}...")

    # Done data
    done = query_result.get("done_data", {})
    if done:
        follow_ups = done.get("follow_ups", [])
        tier = done.get("tier", "unknown")
        print(f"\n  Tier: {tier}")
        print(f"  Follow-up questions: {len(follow_ups)}")

    print("\n" + "=" * 70)

    # Compare mode note
    if hasattr(args, "compare") and args.compare:
        print("\n--- Compare Mode ---")
        print("To compare agentic vs v1 pipeline performance:")
        print("  1. Run this script with ENABLE_AGENTIC_PIPELINE=true  (default)")
        print("  2. Set ENABLE_AGENTIC_PIPELINE=false in .env, restart the API")
        print("  3. Run this script again")
        print("  4. Compare the stage waterfalls side-by-side")
        print("  (Runtime toggle not available — requires API restart)")


async def run(args: argparse.Namespace) -> None:
    import httpx

    print("NEXUS Query Pipeline Diagnostic")
    print(f"  API: {args.api_url}")
    print(f'  Query: "{args.query}"')
    print(f"  Matter: {args.matter_id or '(none — will fail if required)'}")

    # 1. Authenticate
    print("\n[1/3] Authenticating...")
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            token = await authenticate(client, args.api_url, args.email, args.password)
            print(f"  Authenticated as {args.email}")
        except Exception as e:
            print(f"  FAILED: {e}")
            print("  Cannot proceed without auth. Check --email and --password.")
            sys.exit(1)

        headers = {"Authorization": f"Bearer {token}"}

        # 2. Health checks
        print("\n[2/3] Running health checks...")
        try:
            health = await check_health(client, args.api_url, headers)
        except Exception as e:
            print(f"  FAILED: {e}")
            health = {
                "basic": {"status_code": 0, "latency_ms": 0, "body": {}},
                "deep": {"status_code": 0, "latency_ms": 0, "body": {}},
            }

    # 3. Query
    print("\n[3/3] Running query stream...")
    if not args.matter_id:
        print("  SKIPPED: --matter-id required for query")
        query_result = {"error": "no matter-id provided"}
    else:
        async with httpx.AsyncClient(timeout=300.0) as client:
            query_result = await run_query_stream(
                client, args.api_url, headers, args.matter_id, args.query, args.verbose
            )

    print_report(health, query_result, args)


def main() -> None:
    args = parse_args()

    if args.dry_run:
        print("NEXUS Query Diagnostic")
        print(f"Config: api_url={args.api_url}, email={args.email}, matter_id={args.matter_id}")
        print("\n--dry-run: config validated, exiting 0")
        sys.exit(0)

    asyncio.run(run(args))


if __name__ == "__main__":
    main()
