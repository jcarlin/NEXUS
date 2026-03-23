# NEXUS

Multimodal RAG investigation platform for legal document intelligence. Ingests, analyzes, and queries 50,000+ pages of mixed-format legal documents — surfacing people, relationships, timelines, and patterns across a heterogeneous corpus.

## What NEXUS Does

- **Ingest anything** — PDF, DOCX, XLSX, PPTX, HTML, EML, MSG, RTF, CSV, TXT, images, ZIP archives, EDRM load files
- **Ask questions, get cited answers** — 6 autonomous LangGraph agents investigate your corpus with cited, verifiable responses
- **Case intelligence** — extract claims, parties, defined terms, and timelines from anchor documents
- **Investigate relationships** — knowledge graph with entity resolution, email threading, communication analytics, topic clustering
- **Export for court** — annotations, production sets, Bates numbering, redaction, EDRM-compatible output
- **Full auditability** — SOC 2-ready audit trail for every API call and LLM invocation
- **Run anywhere** — 4 LLM providers, 6 embedding providers, CPU or GPU, full local deployment with zero cloud dependency

## Tech Stack

| Component | Technology |
|---|---|
| API | FastAPI |
| Task Queue | Celery + RabbitMQ (Redis fallback) |
| Object Storage | MinIO (S3-compatible) |
| Metadata DB | PostgreSQL 16 |
| Vector DB | Qdrant |
| Knowledge Graph | Neo4j |
| LLM | Claude Sonnet 4.5 (Anthropic), OpenAI, vLLM, Ollama |
| Embeddings | Multi-provider (OpenAI, Ollama, local, Gemini, TEI) |
| NER | GLiNER (zero-shot, CPU) |
| Doc Parsing | Docling (PDF, DOCX, XLSX, PPTX, HTML, images) + stdlib (EML, MSG, RTF, CSV, TXT) |
| Query Orchestration | LangGraph (agentic state graph) |
| Structured Output | Instructor |
| Frontend | React 19 + Vite + TanStack Router + shadcn/ui |

## Prerequisites

- Python 3.12+
- Node.js 20+
- [Docker](https://docs.docker.com/get-docker/) (for infrastructure services)
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- [Anthropic API key](https://console.anthropic.com/)
- [OpenAI API key](https://platform.openai.com/api-keys) (for embeddings — not needed if using Ollama or local)
- [Ollama](https://ollama.com/) (optional — for local LLM inference)

## Quick Start

```bash
git clone <repo-url> && cd NEXUS
cp .env.example .env   # edit API keys
make install            # Python + frontend deps
make dev                # starts everything in one terminal
```

API docs available at http://localhost:8000/docs

## LLM Providers

NEXUS supports 4 LLM providers. Set `LLM_PROVIDER` and the corresponding env vars in `.env`:

| Provider | `LLM_PROVIDER` | Requires |
|----------|----------------|----------|
| Anthropic | `anthropic` | `ANTHROPIC_API_KEY` |
| OpenAI | `openai` | `OPENAI_API_KEY` |
| vLLM | `vllm` | `VLLM_BASE_URL` |
| Ollama | `ollama` | `OLLAMA_BASE_URL` |

vLLM and Ollama both expose OpenAI-compatible APIs, so switching is a config change — no code changes needed. See `.env.local.example` for a full local deployment config.

## Embedding Providers

NEXUS supports 6 embedding providers. Set `EMBEDDING_PROVIDER` in `.env`:

| Provider | `EMBEDDING_PROVIDER` | Default Model | Dimensions | Requires |
|----------|---------------------|---------------|------------|----------|
| OpenAI | `openai` | `text-embedding-3-large` | 1024 | `OPENAI_API_KEY` |
| Ollama | `ollama` | `nomic-embed-text` | 768 | `OLLAMA_BASE_URL` + model pulled |
| Local | `local` | `BAAI/bge-large-en-v1.5` | 1024 | — (auto-downloads) |
| Gemini | `gemini` | `gemini-embedding-exp-03-07` | 1024 | `GEMINI_API_KEY` |
| TEI | `tei` | Any HuggingFace model | varies | `TEI_EMBEDDING_URL` |
| BGE-M3 | `bgem3` | `BAAI/bge-m3` | 1024 | — (auto-downloads, dense+sparse in one pass) |

Ollama and Local providers run entirely on-device — no data leaves the machine. Set `EMBEDDING_DIMENSIONS` to match your model's output size. Changing dimensions requires deleting the Qdrant `nexus_text` collection (auto-recreated on startup).

## Makefile Targets

| Target | What it does |
|--------|-------------|
| `make help` | Show all targets (default) |
| `make install` | Create venv, install Python + frontend deps |
| `make up` | Start Docker infrastructure services |
| `make down` | Stop Docker infrastructure services |
| `make dev` | Start everything: infra + API + worker + frontend (one terminal) |
| `make api` | Start API server with auto-reload |
| `make worker` | Start Celery worker with auto-reload on `.py` changes |
| `make frontend` | Start React frontend dev server |
| `make test` | Run test suite |
| `make migrate` | Run database migrations (Alembic) |
| `make logs` | Tail Docker service logs (filter with `SERVICES=redis,postgres`) |

## Running Tests

```bash
make test
```

Tests mock all external services — no running infrastructure required.

## Load Testing

Locust-based load tests simulate concurrent attorney workflows against the NEXUS API.

```bash
pip install -r load_tests/requirements.txt

# Set required env vars
export NEXUS_TEST_MATTER_ID=<your-matter-uuid>
export NEXUS_TEST_EMAIL=admin@nexus.local
export NEXUS_TEST_PASSWORD=changeme

# Web UI (interactive dashboard at http://localhost:8089)
locust -f load_tests/locustfile.py --host http://localhost:8000

# Headless (10 users, 60s)
locust -f load_tests/locustfile.py --headless -u 10 -r 2 --run-time 60s
```

See [load_tests/README.md](load_tests/README.md) for full configuration, task weights, and CI integration.

## Project Structure

```
nexus/
├── app/
│   ├── main.py                 # FastAPI app factory + lifespan
│   ├── config.py               # Pydantic Settings (all config from env)
│   ├── dependencies.py         # DI: 20 cached factory functions
│   ├── analysis/               # Sentiment scoring, hot doc detection, completeness
│   ├── analytics/              # Communication matrices, network centrality, org hierarchy
│   ├── annotations/            # Document annotations (notes, highlights, tags)
│   ├── audit/                  # Audit log API endpoints
│   ├── auth/                   # JWT auth, RBAC, matter scoping, admin
│   ├── cases/                  # Case Setup Agent, context resolver, claims/parties
│   ├── common/                 # Shared: middleware, storage, LLM client, embedder, vector store
│   ├── datasets/               # Dataset/collection management, folder tree
│   ├── documents/              # Document metadata, preview, download
│   ├── edrm/                   # EDRM load file import/export
│   ├── entities/               # NER, entity resolution agent, knowledge graph
│   ├── evaluation/             # RAG evaluation datasets and runs
│   ├── exports/                # Production sets, Bates numbering, export jobs
│   ├── ingestion/              # Upload → parse → chunk → embed → extract → index
│   ├── query/                  # LangGraph agentic query pipeline + 12 tools + chat
│   └── redaction/              # PII detection, redaction engine
├── workers/
│   └── celery_app.py           # Celery config + task autodiscovery
├── migrations/                 # Alembic migrations (13 revisions)
├── frontend/                   # React 19 + Vite + TanStack Router
├── tests/                      # 512 backend tests (mirrors app/ structure)
├── scripts/                    # cloud-deploy.sh, seed_admin.py, import_dataset.py, evaluate.py
├── docs/                       # modules.md, database-schema.md, feature-flags.md, agents.md, ...
├── docker-compose.yml          # Infrastructure services (dev) + RabbitMQ
├── docker-compose.prod.yml     # Full containerized stack
├── docker-compose.cloud.yml    # Cloud overlay (Caddy + TLS)
├── docker-compose.gpu.yml      # GPU overlay (NVIDIA passthrough for Ollama + TEI)
├── docker-compose.local.yml    # Local LLM stack (vLLM/Ollama, TEI)
├── Caddyfile                   # Reverse proxy config
├── Makefile                    # Dev workflow targets
├── Procfile.dev                # Process definitions for `make dev`
└── pyproject.toml
```

## API Endpoints

Start the server and visit http://localhost:8000/docs for the full interactive OpenAPI documentation.

Key endpoint groups:

- **`/api/v1/auth`** — Authentication and user management
- **`/api/v1/ingest`** — Upload and process documents (single, batch, webhook)
- **`/api/v1/query`** — Query the corpus (sync and SSE streaming)
- **`/api/v1/chats`** — Chat thread management
- **`/api/v1/documents`** — Browse, preview, and download documents
- **`/api/v1/entities`** — Entity search and knowledge graph exploration
- **`/api/v1/cases`** — Case setup and context management
- **`/api/v1/analytics`** — Communication matrices, network centrality
- **`/api/v1/annotations`** — Document annotations (notes, highlights, tags)
- **`/api/v1/exports`** — Production sets, Bates numbering, export jobs
- **`/api/v1/edrm`** — EDRM load file import
- **`/api/v1/redaction`** — PII detection and document redaction
- **`/api/v1/datasets`** — Dataset/collection management
- **`/api/v1/evaluation`** — RAG evaluation datasets and runs
- **`/api/v1/admin`** — User management, audit log (admin-only)
- **`/api/v1/health`** — Service health check

## Feature Flags

Optional capabilities controlled via environment variables. See [docs/feature-flags.md](docs/feature-flags.md) for full details.

| Flag | Default | Description |
|---|---|---|
| `ENABLE_AGENTIC_PIPELINE` | `true` | Agentic LangGraph query pipeline (vs. v1 linear chain) |
| `ENABLE_CITATION_VERIFICATION` | `true` | CoVe citation verification in query synthesis |
| `ENABLE_EMAIL_THREADING` | `true` | Email conversation thread reconstruction |
| `ENABLE_AI_AUDIT_LOGGING` | `true` | Log LLM calls to ai_audit_log table |
| `ENABLE_SPARSE_EMBEDDINGS` | `false` | BM42 sparse vectors for hybrid retrieval |
| `ENABLE_RERANKER` | `false` | Cross-encoder reranking of retrieval results |
| `ENABLE_VISUAL_EMBEDDINGS` | `false` | ColQwen2.5 visual embedding and reranking |
| `ENABLE_RELATIONSHIP_EXTRACTION` | `false` | LLM-based relationship extraction |
| `ENABLE_NEAR_DUPLICATE_DETECTION` | `false` | MinHash near-duplicate and version detection |
| `ENABLE_HOT_DOC_DETECTION` | `false` | Sentiment scoring and hot doc flagging |
| `ENABLE_TOPIC_CLUSTERING` | `false` | BERTopic topic clustering |
| `ENABLE_CASE_SETUP_AGENT` | `false` | Case context pre-population |
| `ENABLE_COREFERENCE_RESOLUTION` | `false` | spaCy + coreferee pronoun resolution |
| `ENABLE_GRAPH_CENTRALITY` | `false` | Neo4j GDS centrality metrics |
| `ENABLE_BATCH_EMBEDDINGS` | `false` | Async batch embedding API (stub) |
| `ENABLE_REDACTION` | `false` | PII detection and document redaction |
| `ENABLE_PROMETHEUS_METRICS` | `false` | Prometheus `/metrics` endpoint + custom business metrics |
| `ENABLE_SSO` | `false` | OIDC/OAuth2 SSO authentication |
| `ENABLE_MEMO_DRAFTING` | `false` | LLM-powered legal memo generation from investigation results |

## Deployment

### CPU (default)
```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.cloud.yml up -d
```

### GPU (NVIDIA T4/L4/A100)
Add the GPU overlay for accelerated embeddings and reranking (~20x faster):
```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  -f docker-compose.cloud.yml -f docker-compose.gpu.yml up -d
```

Requires NVIDIA drivers + [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html). The GPU overlay adds NVIDIA passthrough to Ollama and an optional TEI embedding server. See [docs/CLOUD-DEPLOY.md](docs/CLOUD-DEPLOY.md) for full GPU VM provisioning guide.

### Celery Broker

By default, Celery uses Redis as its message broker. For production, set `CELERY_BROKER_URL` to use RabbitMQ (included in `docker-compose.yml`):

```bash
CELERY_BROKER_URL=amqp://nexus:nexus@rabbitmq:5672/nexus
```

Leave `CELERY_BROKER_URL` empty to fall back to Redis. See [docs/celery-scaling.md](docs/celery-scaling.md) for worker scaling guide.

## See Also

- [ARCHITECTURE.md](ARCHITECTURE.md) — System design, tech stack, data flow, security model
- [ROADMAP.md](ROADMAP.md) — Milestones, build status, dependency graph
- [CLAUDE.md](CLAUDE.md) — Development conventions and implementation rules
- [docs/modules.md](docs/modules.md) — All 16 domain modules with files, schemas, and endpoints
- [docs/database-schema.md](docs/database-schema.md) — 27 tables, 13 migrations, full column reference
- [docs/feature-flags.md](docs/feature-flags.md) — All 16 feature flags with resource impact
- [docs/agents.md](docs/agents.md) — 6 LangGraph agents with state schemas and tools
- [docs/testing-guide.md](docs/testing-guide.md) — Test infrastructure, fixtures, patterns
- [docs/CLOUD-DEPLOY.md](docs/CLOUD-DEPLOY.md) — Cloud deployment guide (GCP + Vercel, CPU + GPU)
- [docs/celery-scaling.md](docs/celery-scaling.md) — Celery worker scaling runbook
- [.env.example](.env.example) — All configuration variables
