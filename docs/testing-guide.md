# Testing Guide

## Overview

- **Backend tests:** 97 test files across 18 test modules (pytest)
- **Frontend tests:** 10 test files -- 7 unit (Vitest) + 3 E2E (Playwright)
- **CI/CD:** 3 GitHub Actions workflows (`test-backend`, `test-frontend`, `evaluate`)

## Directory Structure

```
tests/
├── conftest.py                  # Root fixtures: test settings, client, unauthed_client
├── test_health.py               # Health endpoint tests
├── test_analysis/               # 6 files — anomaly, completeness, hot docs, sentiment, tools
├── test_analytics/              # 6 files — centrality, clustering, communication, org chart
├── test_annotations/            # 1 file  — annotation CRUD
├── test_audit/                  # 1 file  — AI audit logging
├── test_auth/                   # 4 files — middleware, router, service, admin router
├── test_cases/                  # 5 files — case agent, context resolver, extraction
├── test_common/                 # 8 files — config, dependencies, embedder, vector store, rate limit
├── test_datasets/               # 2 files — dataset router, service
├── test_documents/              # 4 files — router, service, privilege, score filters
├── test_e2e/                    # 6 files — full-stack E2E (requires Docker services)
│   ├── conftest.py              # E2E fixtures (session/module scoped, real services)
│   ├── fixtures/                # sample_legal_doc.txt
│   ├── stubs/                   # FakeLLMClient (deterministic canned responses)
│   ├── test_00_health.py
│   ├── test_01_auth.py
│   ├── test_02_ingest.py
│   ├── test_03_documents.py
│   ├── test_04_query.py
│   └── test_05_entities.py
├── test_edrm/                   # 4 files — dedup, loadfile parser, threading, version detection
├── test_entities/               # 7 files — resolver, graph service, coreference, router
├── test_evaluation/             # 7 files — metrics, adversarial, tuning, dataset, CLI
├── test_exports/                # 1 file  — export functionality
├── test_ingestion/              # 15 files — parser, chunker, embedder, router, tasks, webhook, ZIP
├── test_integration/            # 3 files — cross-module integration tests
│   └── conftest.py              # Integration fixtures: mock_services, compiled_graph
├── test_query/                  # 15 files — graph, nodes, retriever, reranker, streaming, tools
└── test_redaction/              # 1 file  — redaction tests

frontend/
├── __tests__/                   # 2 Vitest unit tests (store tests)
│   ├── app-store.test.ts
│   └── auth-store.test.ts
├── src/__tests__/               # 5 Vitest unit/component tests
│   ├── annotations.test.tsx
│   ├── chat.test.tsx
│   ├── dataset-access.test.ts
│   ├── datasets-dnd.test.ts
│   └── review.test.ts
└── e2e/                         # 3 Playwright E2E specs
    ├── login.spec.ts
    ├── query-citation.spec.ts
    └── smoke-all-pages.spec.ts
```

## Running Tests

### Backend

```bash
# Run all backend tests
pytest tests/ -v

# Run with coverage
pytest tests/ -v --cov=app

# Run a single module
pytest tests/test_query/ -v

# Run a single test file
pytest tests/test_ingestion/test_router.py -v

# Run a single test by name
pytest tests/ -v -k "test_ingest_accepts_file"

# Run only E2E tests (requires Docker services running)
pytest tests/test_e2e/ -v -m e2e

# Skip slow tests
pytest tests/ -v -m "not slow"

# Show 10 slowest tests (enabled by default via addopts)
pytest tests/ -v --durations=10
```

### Frontend

```bash
# Unit tests (Vitest)
cd frontend && npm test              # single run
cd frontend && npm run test:watch    # watch mode
cd frontend && npm run test:coverage # with coverage

# E2E tests (Playwright)
cd frontend && npx playwright test
```

## Pytest Configuration

Defined in `pyproject.toml` under `[tool.pytest.ini_options]`:

```toml
asyncio_mode = "auto"               # All async tests run automatically (no per-test marker needed)
testpaths = ["tests"]               # Default test discovery path
addopts = "--durations=10"          # Always show 10 slowest tests
filterwarnings = ["ignore::DeprecationWarning"]
markers = [
    "e2e: End-to-end tests requiring real Docker services",
    "slow: Tests that take more than 10 seconds",
]
```

### Test Dependencies

All test dependencies are in the `[project.optional-dependencies] dev` group:

| Package | Purpose |
|---|---|
| `pytest>=8.0` | Test runner |
| `pytest-asyncio>=0.24` | Async test support |
| `pytest-cov>=5.0` | Coverage reporting |
| `httpx>=0.27` | Async HTTP client for FastAPI test client |
| `ruff>=0.8` | Linting |
| `mypy>=1.13` | Type checking |
| `ragas>=0.1.10` | RAG evaluation metrics |
| `datasets>=2.14` | Evaluation dataset handling |

Install with:

```bash
uv pip install -e ".[dev]"
```

## Key Fixtures (from `tests/conftest.py`)

### `test_settings`

**Scope:** function

Provides a `Settings` instance with safe test defaults. All connection strings point to localhost with test credentials. No real service connections are attempted.

```python
@pytest.fixture()
def test_settings() -> Settings:
    return Settings(
        anthropic_api_key="test-key",
        openai_api_key="test-key",
        llm_provider="anthropic",
        postgres_url="postgresql+asyncpg://nexus:test@localhost:5432/nexus_test",
        redis_url="redis://localhost:6379/15",
        qdrant_url="http://localhost:6333",
        neo4j_uri="bolt://localhost:7687",
        neo4j_password="test",
        minio_endpoint="localhost:9000",
        minio_access_key="test",
        minio_secret_key="test",
    )
```

### `client`

**Scope:** function

Provides an `httpx.AsyncClient` wired directly to the FastAPI ASGI app. All external services are patched out -- no Docker infrastructure required.

Key behaviors:
- **Lifespan is patched** to a no-op (no service connections on startup).
- **Auth is overridden** -- `get_current_user` returns a test admin user, `get_matter_id` returns a default matter UUID. Tests do not need auth headers.
- **Rate limiters** are overridden to no-op.
- App is re-created via `main_module.create_app()` with the patched lifespan.

```python
@pytest.fixture()
async def client() -> AsyncIterator[AsyncClient]:
    # Patches lifespan, overrides auth + rate limiters
    # Yields AsyncClient at http://testserver
```

Test user identity:
- **ID:** `00000000-0000-0000-0000-000000000099`
- **Email:** `test@nexus.dev`
- **Role:** `admin`
- **Matter ID:** `00000000-0000-0000-0000-000000000001`

### `unauthed_client`

**Scope:** function

Same as `client` but **without auth overrides**. Used by auth-specific tests (`test_auth/test_middleware.py`) to exercise the real auth middleware, JWT validation, matter scoping, and RBAC.

Rate limiters are still disabled.

## Key Fixtures (from `tests/test_integration/conftest.py`)

### `mock_services`

**Scope:** function

Returns a `dict` with mocked service dependencies for the query graph:

| Key | Type | Behavior |
|---|---|---|
| `llm` | `AsyncMock` | `.complete()` returns `"factual"`, `.stream()` yields a canned answer |
| `retriever` | `AsyncMock` | `.retrieve_all()` returns 2 text results + 1 graph relationship |
| `graph_service` | `AsyncMock` | `.get_entity_connections()` returns `[]` |
| `entity_extractor` | `MagicMock` | `.extract()` returns one `FakeEntity("John Doe", "person")` |

### `compiled_graph`

**Scope:** function

Returns a compiled LangGraph using the real `build_graph()` function with the `mock_services` dependencies injected. Used for integration tests that exercise the full graph pipeline with mocked external calls.

## Testing Patterns

### Async Tests

The project uses `pytest-asyncio` with `asyncio_mode = "auto"` in `pyproject.toml`. This means:

- **All `async def test_*` functions are automatically treated as async tests.** You do not need `@pytest.mark.asyncio` (though many existing tests still include it for explicitness).
- Async fixtures (`async def`) also work automatically.

```python
# Both of these work:

@pytest.mark.asyncio
async def test_explicit_marker(client: AsyncClient):
    resp = await client.get("/api/v1/health")
    assert resp.status_code != 401

async def test_auto_mode(client: AsyncClient):
    resp = await client.get("/api/v1/health")
    assert resp.status_code != 401
```

### Mocking External Services

The standard pattern is to use `unittest.mock.patch` on the module where the dependency is imported, not where it is defined. Service methods use `AsyncMock` for async methods and `MagicMock` for sync code.

**Router-level tests** (most common pattern): patch at the router import path.

```python
from unittest.mock import AsyncMock, MagicMock, patch

async def test_ingest_accepts_file(client: AsyncClient):
    mock_storage = MagicMock()
    mock_storage.upload_bytes = AsyncMock(return_value="raw/test/file.txt")

    with (
        patch("app.ingestion.router.get_minio", return_value=mock_storage),
        patch("app.ingestion.router.process_document") as mock_task,
        patch("app.ingestion.service.IngestionService.create_job",
              new_callable=AsyncMock) as mock_create,
    ):
        mock_task.delay = MagicMock()        # Celery .delay() is sync
        mock_create.return_value = fake_job

        response = await client.post(
            "/api/v1/ingest",
            files={"file": ("test.txt", b"Hello world", "text/plain")},
        )
    assert response.status_code == 200
```

**Auth middleware tests**: use the `unauthed_client` fixture and patch `app.auth.middleware.*`.

```python
async def test_valid_jwt_passes(unauthed_client: AsyncClient):
    token = _make_token(str(_FAKE_USER.id))
    with (
        patch("app.auth.middleware.get_settings", return_value=_SETTINGS),
        patch("app.auth.middleware.AuthService.get_user_by_id",
              new_callable=AsyncMock, return_value=_FAKE_USER),
        patch("app.auth.middleware.AuthService.matter_exists",
              new_callable=AsyncMock, return_value=True),
        patch("app.auth.middleware.AuthService.check_user_matter_access",
              new_callable=AsyncMock, return_value=True),
    ):
        resp = await unauthed_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
```

### Celery Task Testing

Celery's `.delay()` method is **synchronous** -- always mock it with `MagicMock`, never `AsyncMock`.

```python
# Correct:
mock_task.delay = MagicMock()

# Wrong:
mock_task.delay = AsyncMock()  # .delay() is not async
```

For testing the actual task stage functions (which run synchronously inside Celery workers), call them directly with mocked dependencies:

```python
from app.ingestion.tasks import _stage_parse, _PipelineContext

def test_stage_parse_populates_context():
    ctx = _make_ctx()  # helper that builds a _PipelineContext with mocks
    with (
        patch("app.ingestion.tasks._update_stage"),
        patch("app.ingestion.tasks._download_from_minio", return_value=b"bytes"),
        patch("app.ingestion.tasks._upload_to_minio"),
        patch("app.ingestion.parser.DocumentParser") as mock_parser,
    ):
        mock_parser.return_value.parse.return_value = _FakeParseResult()
        _stage_parse(ctx)

    assert ctx.parse_result is not None
    assert ctx.file_size == len(b"bytes")
```

The `_stage_complete` test demonstrates the Celery `.delay()` mock pattern for chained tasks:

```python
with patch("app.entities.tasks.resolve_entities") as mock_resolve:
    mock_resolve.delay = MagicMock()
    _stage_complete(ctx)
```

### LangGraph Testing

The query graph is tested at multiple levels:

1. **Unit tests** (`test_query/test_graph.py`): Test graph construction and routing logic with simple mocks.
2. **Integration tests** (`test_integration/`): Use `build_graph()` with mocked services, then `await compiled.ainvoke(initial_state)` to run the full graph.

```python
async def test_graph_invoke_end_to_end(mock_llm, mock_retriever, ...):
    graph = build_graph(mock_llm, mock_retriever, mock_graph_service, mock_entity_extractor)
    compiled = graph.compile()
    final_state = await compiled.ainvoke(initial_state)
    assert final_state["query_type"] == "factual"
    assert len(final_state["response"]) > 0
```

## E2E Tests

### Overview

E2E tests live in `tests/test_e2e/` and exercise the full stack with real Docker services. They are numbered (`test_00_*` through `test_05_*`) to enforce execution order.

### Requirements

All 5 Docker services must be running:
- **PostgreSQL** (port 5432)
- **Redis** (port 6379)
- **Qdrant** (port 6333)
- **Neo4j** (port 7687)
- **MinIO** (port 9000)

Start them with:

```bash
docker compose up -d
```

Tests skip gracefully if any service is unreachable (via the `e2e_services_check` fixture).

### E2E Fixture Hierarchy

The E2E conftest defines a layered fixture hierarchy:

**Session-scoped** (run once per test session):

| Fixture | Purpose |
|---|---|
| `e2e_env_vars` | Isolates environment variables (test DB, Redis DB 14, local embeddings at 384d) |
| `e2e_services_check` | Pings all 5 services; skips suite if any is unreachable |
| `e2e_postgres_db` | Creates `nexus_e2e_test` database, runs Alembic migrations, drops on teardown |
| `e2e_qdrant` | Creates `nexus_text` collection with 384d vectors, deletes on teardown |
| `e2e_neo4j` | Clears all graph data, ensures schema, clears on teardown |
| `e2e_minio` | Creates `e2e-test` bucket, cleans up all objects + bucket on teardown |
| `e2e_redis` | Flushes Redis DB 14 before and after |
| `celery_eager` | Enables `task_always_eager=True` so Celery tasks run synchronously in-process |

**Module-scoped** (run once per test file):

| Fixture | Purpose |
|---|---|
| `e2e_app` | Creates FastAPI app with real lifespan, overrides LLM with `FakeLLMClient`, disables rate limiters |
| `e2e_client` | `httpx.AsyncClient` wired to the E2E app |
| `admin_auth_headers` | Logs in as seed admin, returns `{"Authorization": "Bearer ...", "X-Matter-ID": "..."}` |
| `attorney_auth_headers` | Creates + logs in attorney user |
| `reviewer_auth_headers` | Creates + logs in reviewer user |
| `ingested_document` | Uploads `sample_legal_doc.txt` and waits for the full ingestion pipeline to complete |

**Function-scoped:**

| Fixture | Purpose |
|---|---|
| `sample_txt_file` | Returns a `BytesIO` with the sample legal doc content |

### FakeLLMClient

The E2E tests use a deterministic `FakeLLMClient` (`tests/test_e2e/stubs/llm_stub.py`) instead of calling real LLM APIs. It pattern-matches on prompt content to return canned responses:

- `"classify"` in prompt --> returns `"factual"`
- `"rewrite"` in prompt --> echoes back the user's query
- `"synthesize"` / `"answer"` in prompt --> returns a canned legal analysis with citation
- Default --> `"Test response based on provided context."`

Both `complete()` and `stream()` methods are implemented. The `stream()` method splits the complete response into word tokens.

### E2E Embedding Configuration

E2E tests use a **local embedding model** to avoid OpenAI API calls:

- **Model:** `BAAI/bge-small-en-v1.5`
- **Dimensions:** 384
- All feature flags (sparse embeddings, visual embeddings, reranker, etc.) are disabled.

### Running E2E Tests

```bash
# Start infrastructure
docker compose up -d

# Run E2E tests only
pytest tests/test_e2e/ -v

# Run with the e2e marker
pytest tests/ -v -m e2e
```

## CI/CD Workflows

All workflow files are in `.github/workflows/`.

### 1. Backend Tests (`test-backend.yml`)

**Triggers:** Push or PR to `main` when `app/`, `tests/`, `workers/`, `pyproject.toml`, `evaluation/`, or `scripts/` change.

**Steps:**
1. Checkout code
2. Install `uv` (with caching enabled via `astral-sh/setup-uv@v4`)
3. Install Python 3.12
4. Install dependencies: `uv sync --extra dev`
5. Run tests: `uv run pytest tests/ -v --tb=short`

This runs unit and integration tests only (no Docker services, so E2E tests are skipped).

### 2. Frontend Tests (`test-frontend.yml`)

**Triggers:** Push or PR to `main` when `frontend/` changes.

**Two parallel jobs:**

**Unit (Vitest):**
1. Checkout, setup Node.js 20 (npm cache from `frontend/package-lock.json`)
2. `npm ci`
3. `npm test` (runs `vitest run`)

**E2E (Playwright):**
1. Checkout, setup Node.js 20
2. `npm ci`
3. `npx playwright install --with-deps chromium`
4. `npx playwright test`

### 3. Evaluation Dry Run (`evaluate.yml`)

**Triggers:** Push or PR to `main` when `app/`, `evaluation/`, or `scripts/` change.

**Steps:**
1. Checkout code
2. Install `uv` + Python 3.12
3. `uv sync --extra dev`
4. `uv run python scripts/evaluate.py --dry-run`

This validates the evaluation pipeline configuration without running actual LLM calls.

## Writing New Tests

### Checklist

1. **Place the test file** in the matching `tests/test_{domain}/` directory.
2. **Use the `client` fixture** for API-level tests (auth is pre-configured).
3. **Use `unauthed_client`** only when testing auth/middleware behavior.
4. **Mock external services** at the import site, not the definition site.
5. **Use `MagicMock` for Celery `.delay()`**, `AsyncMock` for async service methods.
6. **Follow the naming convention:** `test_{module}/test_{feature}.py`, functions named `test_{behavior}`.
7. **Keep tests independent.** Each test should set up its own mocks and not rely on state from other tests.
8. **Match existing patterns.** Look at the nearest existing test file in the same module for conventions.

### Example: Testing a New Router Endpoint

```python
"""Tests for the widgets API endpoints."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_widgets_returns_empty(client: AsyncClient) -> None:
    """GET /widgets with no data returns empty list."""
    with patch(
        "app.widgets.service.WidgetService.list_widgets",
        new_callable=AsyncMock,
        return_value=([], 0),
    ):
        response = await client.get("/api/v1/widgets")

    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["total"] == 0
```

### Example: Testing a Celery Task Stage

```python
"""Tests for the widget processing task."""

from unittest.mock import MagicMock, patch

from app.widgets.tasks import _stage_process


def test_stage_process_populates_result():
    ctx = _make_ctx()  # build a context with mocked settings + engine

    with (
        patch("app.widgets.tasks._update_stage"),
        patch("app.widgets.tasks._do_processing", return_value="done"),
    ):
        _stage_process(ctx)

    assert ctx.result == "done"
```
