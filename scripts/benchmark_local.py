#!/usr/bin/env python3
"""Benchmark local deployment performance.

Measures embedding, reranking, and LLM throughput against locally hosted
services (TEI, vLLM).  Requires running infrastructure — use ``--dry-run``
for CI validation (prints config and exits 0).

Usage::

    # Dry run (CI — no services required)
    python scripts/benchmark_local.py --dry-run

    # Full benchmark
    python scripts/benchmark_local.py --output results.json

    # Custom service URLs
    python scripts/benchmark_local.py \\
        --tei-embedding-url http://gpu-server:8081 \\
        --tei-reranker-url http://gpu-server:8082 \\
        --vllm-url http://gpu-server:8080/v1
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark NEXUS local deployment")
    parser.add_argument("--dry-run", action="store_true", help="Print config and exit 0 (CI mode)")
    parser.add_argument("--output", type=str, default=None, help="Write results to JSON file")
    parser.add_argument("--tei-embedding-url", type=str, default="http://localhost:8081")
    parser.add_argument("--tei-reranker-url", type=str, default="http://localhost:8082")
    parser.add_argument("--vllm-url", type=str, default="http://localhost:8080/v1")
    parser.add_argument("--query-url", type=str, default="http://localhost:8000/api/v1/query")
    parser.add_argument("--embedding-dims", type=int, default=1024)
    parser.add_argument("--num-texts", type=int, default=100, help="Number of texts for embedding benchmark")
    parser.add_argument("--num-rerank", type=int, default=50, help="Number of passages for reranking benchmark")
    parser.add_argument("--num-queries", type=int, default=10, help="Number of E2E queries for latency benchmark")
    return parser.parse_args()


SAMPLE_TEXTS = [
    "The defendant was observed at the location on January 15, 2024.",
    "Financial records indicate a wire transfer of $50,000 on March 3.",
    "Email correspondence between the parties reveals prior knowledge.",
    "The contract was signed by both parties on February 10, 2023.",
    "Witness testimony corroborates the timeline of events described.",
]

SAMPLE_QUERY = "What were the key financial transactions between the parties?"


async def benchmark_embeddings(url: str, dims: int, num_texts: int) -> dict:
    """Measure embedding throughput (texts/sec)."""
    import httpx

    texts = (SAMPLE_TEXTS * ((num_texts // len(SAMPLE_TEXTS)) + 1))[:num_texts]

    async with httpx.AsyncClient(timeout=120.0) as client:
        start = time.perf_counter()
        response = await client.post(
            f"{url}/embed",
            json={"inputs": texts, "truncate": True},
        )
        elapsed = time.perf_counter() - start

    response.raise_for_status()
    embeddings = response.json()

    return {
        "num_texts": len(texts),
        "elapsed_sec": round(elapsed, 3),
        "texts_per_sec": round(len(texts) / elapsed, 1),
        "output_dim": len(embeddings[0]) if embeddings else 0,
    }


async def benchmark_reranking(url: str, num_passages: int) -> dict:
    """Measure reranking throughput (pairs/sec)."""
    import httpx

    texts = (SAMPLE_TEXTS * ((num_passages // len(SAMPLE_TEXTS)) + 1))[:num_passages]

    async with httpx.AsyncClient(timeout=120.0) as client:
        start = time.perf_counter()
        response = await client.post(
            f"{url}/rerank",
            json={"query": SAMPLE_QUERY, "texts": texts, "truncate": True},
        )
        elapsed = time.perf_counter() - start

    response.raise_for_status()

    return {
        "num_passages": len(texts),
        "elapsed_sec": round(elapsed, 3),
        "pairs_per_sec": round(len(texts) / elapsed, 1),
    }


async def benchmark_llm(vllm_url: str) -> dict:
    """Measure LLM first-token latency and tokens/sec."""
    import httpx

    prompt = (
        "You are a legal analyst. Summarize the key issues in a breach of "
        "contract dispute involving a technology licensing agreement."
    )

    async with httpx.AsyncClient(timeout=120.0) as client:
        start = time.perf_counter()
        response = await client.post(
            f"{vllm_url}/chat/completions",
            json={
                "model": "default",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 256,
                "temperature": 0.1,
                "stream": False,
            },
        )
        elapsed = time.perf_counter() - start

    response.raise_for_status()
    data = response.json()

    output_tokens = data.get("usage", {}).get("completion_tokens", 0)

    return {
        "elapsed_sec": round(elapsed, 3),
        "output_tokens": output_tokens,
        "tokens_per_sec": round(output_tokens / elapsed, 1) if elapsed > 0 else 0,
    }


async def benchmark_e2e(query_url: str, num_queries: int) -> dict:
    """Measure E2E query p95 latency."""
    import httpx

    queries = [
        "Who are the key parties in this matter?",
        "What financial transactions occurred?",
        "Summarize the timeline of events.",
        "What evidence supports the plaintiff's claim?",
        "Are there any privilege issues?",
    ]

    latencies: list[float] = []
    async with httpx.AsyncClient(timeout=300.0) as client:
        for i in range(num_queries):
            query = queries[i % len(queries)]
            start = time.perf_counter()
            try:
                await client.post(
                    query_url,
                    json={"query": query, "matter_id": "benchmark"},
                    headers={"Authorization": "Bearer benchmark-token"},
                )
                elapsed = time.perf_counter() - start
                latencies.append(elapsed)
            except httpx.HTTPError:
                elapsed = time.perf_counter() - start
                latencies.append(elapsed)

    if not latencies:
        return {"error": "no queries completed"}

    latencies.sort()
    p95_idx = int(len(latencies) * 0.95)

    return {
        "num_queries": num_queries,
        "p50_sec": round(statistics.median(latencies), 3),
        "p95_sec": round(latencies[min(p95_idx, len(latencies) - 1)], 3),
        "mean_sec": round(statistics.mean(latencies), 3),
    }


async def run_benchmarks(args: argparse.Namespace) -> dict:
    """Run all benchmarks and return results dict."""
    results: dict = {}

    print("--- Embedding Benchmark ---")
    try:
        results["embedding"] = await benchmark_embeddings(args.tei_embedding_url, args.embedding_dims, args.num_texts)
        print(f"  {results['embedding']['texts_per_sec']} texts/sec")
    except Exception as e:
        results["embedding"] = {"error": str(e)}
        print(f"  FAILED: {e}")

    print("--- Reranking Benchmark ---")
    try:
        results["reranking"] = await benchmark_reranking(args.tei_reranker_url, args.num_rerank)
        print(f"  {results['reranking']['pairs_per_sec']} pairs/sec")
    except Exception as e:
        results["reranking"] = {"error": str(e)}
        print(f"  FAILED: {e}")

    print("--- LLM Benchmark ---")
    try:
        results["llm"] = await benchmark_llm(args.vllm_url)
        print(f"  {results['llm']['tokens_per_sec']} tokens/sec")
    except Exception as e:
        results["llm"] = {"error": str(e)}
        print(f"  FAILED: {e}")

    print("--- E2E Query Benchmark ---")
    try:
        results["e2e"] = await benchmark_e2e(args.query_url, args.num_queries)
        print(f"  p95: {results['e2e']['p95_sec']}s")
    except Exception as e:
        results["e2e"] = {"error": str(e)}
        print(f"  FAILED: {e}")

    return results


def main() -> None:
    args = parse_args()

    config = {
        "tei_embedding_url": args.tei_embedding_url,
        "tei_reranker_url": args.tei_reranker_url,
        "vllm_url": args.vllm_url,
        "query_url": args.query_url,
        "embedding_dims": args.embedding_dims,
        "num_texts": args.num_texts,
        "num_rerank": args.num_rerank,
        "num_queries": args.num_queries,
    }

    print("NEXUS Local Deployment Benchmark")
    print(f"Config: {json.dumps(config, indent=2)}")

    if args.dry_run:
        print("\n--dry-run: config validated, exiting 0")
        sys.exit(0)

    results = asyncio.run(run_benchmarks(args))
    results["config"] = config

    print(f"\n--- Results ---\n{json.dumps(results, indent=2)}")

    if args.output:
        with open(args.output, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nResults written to {args.output}")


if __name__ == "__main__":
    main()
