# Tests — Quick Reference

## Quick Reference

| Command | What it runs | Prerequisites |
|---|---|---|
| `make test` | All backend unit + integration tests | `make install` |
| `pytest tests/ -v` | Same as above | venv activated |
| `pytest tests/test_query/ -v` | Single module | venv activated |
| `pytest tests/ -v -k "test_name"` | Single test by name | venv activated |
| `pytest tests/ -v -m "not slow"` | Skip slow tests | venv activated |
| `pytest tests/ -v --cov=app` | Backend tests with coverage | venv activated |
| `pytest tests/test_e2e/ -v` | Backend E2E (real services) | `docker compose up -d` |
| `cd frontend && npm test` | Frontend unit tests (Vitest) | `npm install` |
| `cd frontend && npm run test:watch` | Frontend unit tests (watch mode) | `npm install` |
| `cd frontend && npm run test:coverage` | Frontend unit tests with coverage | `npm install` |
| `cd frontend && npm run e2e` | Frontend E2E (Playwright) | `npx playwright install` |
| `python scripts/evaluate.py --dry-run` | Evaluation dry run (no infra) | `uv pip install -e ".[dev]"` |
| `python scripts/evaluate.py` | Full evaluation run | Running services + LLM API |

## Backend (pytest)

97 test files across 18 modules. All tests mock external services — no Docker required for unit/integration tests.

```bash
# All tests
pytest tests/ -v

# Single module
pytest tests/test_query/ -v

# Single file
pytest tests/test_ingestion/test_router.py -v

# Single test by name
pytest tests/ -v -k "test_ingest_accepts_file"

# With coverage
pytest tests/ -v --cov=app

# Skip slow tests
pytest tests/ -v -m "not slow"
```

### Markers

| Marker | Meaning |
|---|---|
| `e2e` | Requires real Docker services (Postgres, Redis, Qdrant, Neo4j, MinIO) |
| `slow` | Takes more than 10 seconds |

### E2E Tests

Backend E2E tests (`tests/test_e2e/`) run against real Docker services with a deterministic `FakeLLMClient` (no LLM API calls).

```bash
docker compose up -d          # Start infrastructure
pytest tests/test_e2e/ -v     # Run E2E suite
```

Tests skip gracefully if services are unreachable.

## Frontend

7 Vitest unit tests + 3 Playwright E2E specs.

```bash
cd frontend

# Unit tests
npm test                      # Single run (vitest run)
npm run test:watch            # Watch mode
npm run test:coverage         # With coverage

# E2E tests
npx playwright install        # First time only
npm run e2e                   # Run Playwright specs
```

## Evaluation

The evaluation pipeline (`scripts/evaluate.py`) measures retrieval quality (MRR, Recall, NDCG), faithfulness, and citation accuracy.

```bash
# Dry run — synthetic data, no infrastructure needed
python scripts/evaluate.py --dry-run

# Full run — requires running services + LLM API
python scripts/evaluate.py --output results.json

# Skip RAGAS metrics
python scripts/evaluate.py --skip-ragas

# Tuning sweep
python scripts/evaluate.py --dry-run --tune

# Config override
python scripts/evaluate.py --dry-run --config-override RETRIEVAL_TEXT_LIMIT=30
```

## CI/CD (GitHub Actions)

Three workflows in `.github/workflows/`:

| Workflow | File | Trigger | What it runs |
|---|---|---|---|
| Backend Tests | `test-backend.yml` | Push/PR to `main` (backend files) | `pytest tests/ -v --tb=short` (no Docker, E2E skipped) |
| Frontend Tests | `test-frontend.yml` | Push/PR to `main` (`frontend/`) | Vitest unit + Playwright E2E (parallel jobs) |
| Evaluation | `evaluate.yml` | Push/PR to `main` (backend + eval files) | `scripts/evaluate.py --dry-run` |

## Further Reading

See [`docs/testing-guide.md`](../docs/testing-guide.md) for:
- Fixture reference (`client`, `unauthed_client`, `mock_services`, `compiled_graph`)
- E2E fixture hierarchy and `FakeLLMClient` details
- Mocking patterns (routers, auth, Celery tasks, LangGraph)
- Writing new tests checklist and examples
