# NEXUS Load Tests

Locust-based concurrent load testing suite that simulates attorney workflows
against the NEXUS platform. Tests document browsing, entity search,
investigation queries, file upload concurrency, and health checks.

## Prerequisites

```bash
pip install -r load_tests/requirements.txt
```

A running NEXUS instance is required. Start one locally with `make dev` or
point to a deployed environment.

## Configuration

All settings are read from environment variables:

| Variable | Default | Description |
|---|---|---|
| `NEXUS_TARGET_HOST` | `http://localhost:8000` | Base URL of the NEXUS API |
| `NEXUS_TEST_EMAIL` | `admin@nexus.local` | Login email for the test user |
| `NEXUS_TEST_PASSWORD` | `changeme` | Login password |
| `NEXUS_TEST_MATTER_ID` | *(empty)* | Matter UUID to scope all data requests |
| `NEXUS_QUERY_POOL` | 8 built-in queries | Pipe-delimited list of test queries |

`NEXUS_TEST_MATTER_ID` **must** be set to a valid matter UUID -- all data
endpoints require it via the `X-Matter-ID` header.

## Usage

### Web UI mode

```bash
locust -f load_tests/locustfile.py --host http://localhost:8000
```

Open http://localhost:8089, enter the number of users and spawn rate, and
start the test. The dashboard shows live request stats, response times, and
failure rates.

### Headless mode

```bash
locust -f load_tests/locustfile.py \
    --headless \
    --host http://localhost:8000 \
    -u 10 \
    -r 2 \
    --run-time 60s
```

Runs 10 concurrent users (spawning 2/sec) for 60 seconds and prints a
summary table to stdout.

### CSV export

```bash
locust -f load_tests/locustfile.py \
    --headless \
    --host http://localhost:8000 \
    -u 5 \
    -r 1 \
    --run-time 30s \
    --csv results/load_test
```

Writes `results/load_test_stats.csv`, `results/load_test_failures.csv`, and
`results/load_test_stats_history.csv`.

## Task weights

Tasks are weighted to model realistic attorney usage:

| Weight | Endpoint | Description |
|---|---|---|
| 5 | `GET /api/v1/documents` | Paginated document browsing |
| 3 | `GET /api/v1/entities` | Entity search with type filters |
| 2 | `POST /api/v1/query` | Investigation query (full pipeline) |
| 1 | `GET /api/v1/health` | Baseline latency |
| 1 | `POST /api/v1/ingest` | File upload concurrency |

## Interpreting results

Key metrics to watch:

- **Median / p95 response time**: Documents and entities should be <500ms.
  Queries will be slower (10-60s depending on LLM backend).
- **Failure rate**: Should be 0% for documents/entities/health. Query
  failures may indicate rate limiting or LLM timeouts.
- **RPS (requests per second)**: Throughput under concurrent load. Compare
  against single-user baseline from `scripts/benchmark_local.py`.
- **Current users**: Ramp up gradually to find the concurrency ceiling
  before error rates spike.

## CI integration

The GitHub Actions workflow (`.github/workflows/load-test.yml`) runs a
headless smoke test on manual trigger. It requires `NEXUS_TARGET_HOST`,
`NEXUS_TEST_EMAIL`, `NEXUS_TEST_PASSWORD`, and `NEXUS_TEST_MATTER_ID` to
be configured as repository secrets.
