# NEXUS

Multimodal RAG investigation platform for legal document intelligence. Ingests, analyzes, and queries 50,000+ pages of mixed-format legal documents — surfacing people, relationships, timelines, and patterns across a heterogeneous corpus.

## What NEXUS Does

- **Ingest anything** — PDF, DOCX, XLSX, PPTX, HTML, EML, MSG, RTF, CSV, TXT, images, ZIP archives, EDRM load files
- **Ask questions, get cited answers** — 6 autonomous LangGraph agents investigate your corpus with cited, verifiable responses
- **Case intelligence** — extract claims, parties, defined terms, and timelines from anchor documents
- **Investigate relationships** — knowledge graph with entity resolution, email threading, communication analytics, topic clustering
- **Export for court** — annotations, production sets, Bates numbering, redaction, EDRM-compatible output
- **Full auditability** — SOC 2-ready audit trail for every API call and LLM invocation
- **Run anywhere** — 4 LLM providers, 6 embedding providers, full local deployment with zero cloud dependency

## Tech Stack

| Component | Technology |
|---|---|
| API | FastAPI |
| Task Queue | Celery + Redis |
| Object Storage | MinIO (S3-compatible) |
| Metadata DB | PostgreSQL 16 |
| Vector DB | Qdrant |
| Knowledge Graph | Neo4j |
| LLM | Claude Sonnet 4.5 (Anthropic), OpenAI, vLLM, Ollama |
| Embeddings | Multi-provider (OpenAI, Ollama, local, Gemini, TEI, BGE-M3) |
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
| BGE-M3 | `bgem3` | `BAAI/bge-m3` | 1024 | — (auto-downloads) |

Ollama, Local, and BGE-M3 providers run entirely on-device — no data leaves the machine. BGE-M3 produces dense+sparse vectors in a single forward pass. Set `EMBEDDING_DIMENSIONS` to match your model's output size. Changing dimensions requires deleting the Qdrant `nexus_text` collection (auto-recreated on startup).

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
│   ├── dependencies.py         # DI: 23 cached factory functions
│   ├── analysis/               # Sentiment scoring, hot doc detection, completeness
│   ├── analytics/              # Communication matrices, network centrality, topic clustering, GraphRAG communities
│   ├── annotations/            # Document annotations (notes, highlights, tags)
│   ├── audit/                  # Audit log API endpoints
│   ├── auth/                   # JWT auth, RBAC, OIDC/SAML SSO, matter scoping, admin
│   ├── cases/                  # Case Setup Agent, context resolver, claims/parties
│   ├── common/                 # Shared: middleware, storage, LLM client, embedder, vector store, metrics
│   ├── datasets/               # Dataset/collection management, folder tree
│   ├── depositions/            # Deposition prep workflow (witness profiling, question generation)
│   ├── documents/              # Document metadata, preview, download, comparison/redline
│   ├── edrm/                   # EDRM load file import/export
│   ├── entities/               # NER, entity resolution agent, knowledge graph
│   ├── evaluation/             # RAG evaluation datasets and runs
│   ├── exports/                # Production sets, Bates numbering, export jobs
│   ├── feature_flags/          # Runtime feature flag registry and admin UI
│   ├── gdrive/                 # Google Drive OAuth connector
│   ├── ingestion/              # Upload → parse → chunk → embed → extract → index
│   ├── llm_config/             # Runtime LLM provider CRUD, tier assignment, model discovery
│   ├── memos/                  # LLM-powered legal memo drafting
│   ├── operations/             # Docker/Celery service management UI
│   ├── query/                  # LangGraph agentic query pipeline + 17 tools + chat
│   ├── redaction/              # PII detection, redaction engine
│   ├── retention/              # Data retention policy enforcement
│   └── settings_registry/      # Runtime settings tuning admin UI
├── workers/
│   └── celery_app.py           # Celery config + task autodiscovery
├── migrations/                 # Alembic migrations (30 revisions)
├── frontend/                   # React 19 + Vite + TanStack Router
├── helm/                       # Kubernetes Helm charts
├── tests/                      # ~1528 backend tests (mirrors app/ structure)
├── scripts/                    # cloud-deploy.sh, seed_admin.py, import_dataset.py, evaluate.py
├── docs/                       # modules.md, database-schema.md, feature-flags.md, agents.md, ...
├── monitoring/                 # Prometheus + Grafana stack (docker-compose.monitoring.yml)
├── load_tests/                 # Locust load testing suite with SLA assertions
├── docker-compose.yml          # Infrastructure services (dev)
├── docker-compose.prod.yml     # Full containerized stack
├── docker-compose.cloud.yml    # Cloud overlay (Caddy + TLS)
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
- **`/api/v1/llm-config`** — Runtime LLM provider CRUD and tier assignment
- **`/api/v1/feature-flags`** — Runtime feature flag management
- **`/api/v1/settings`** — Runtime settings tuning
- **`/api/v1/retention`** — Data retention policy management
- **`/api/v1/memos`** — Legal memo drafting (feature-flagged)
- **`/api/v1/depositions`** — Deposition prep workflow (feature-flagged)
- **`/api/v1/operations`** — Service operations management (feature-flagged)
- **`/api/v1/gdrive`** — Google Drive connector (feature-flagged)
- **`/api/v1/admin`** — User management, audit log (admin-only)
- **`/api/v1/health`** — Service health check

## Feature Flags

48 optional capabilities controlled via environment variables (45 runtime-toggleable via admin UI). See [docs/feature-flags.md](docs/feature-flags.md) for full details.

**Enabled by default:**

| Flag | Default | Description |
|---|---|---|
| `ENABLE_AGENTIC_PIPELINE` | `true` | Agentic LangGraph query pipeline (vs. v1 linear chain) |
| `ENABLE_CITATION_VERIFICATION` | `true` | CoVe citation verification in query synthesis |
| `ENABLE_EMAIL_THREADING` | `true` | Email conversation thread reconstruction |
| `ENABLE_AI_AUDIT_LOGGING` | `true` | Log LLM calls to ai_audit_log table |
| `ENABLE_RERANKER` | `true` | Cross-encoder reranking of retrieval results |
| `ENABLE_NEAR_DUPLICATE_DETECTION` | `true` | MinHash near-duplicate and version detection |
| `ENABLE_PROMETHEUS_METRICS` | `true` | Prometheus `/metrics` endpoint + custom business metrics |

**Opt-in (default off):**

| Flag | Default | Description |
|---|---|---|
| `ENABLE_SPARSE_EMBEDDINGS` | `false` | BM42 sparse vectors for hybrid retrieval |
| `ENABLE_SPLADE_SPARSE` | `false` | SPLADE v3 learned sparse retrieval (asymmetric doc/query) |
| `ENABLE_VISUAL_EMBEDDINGS` | `false` | ColQwen2.5 visual embedding and reranking |
| `ENABLE_RELATIONSHIP_EXTRACTION` | `false` | LLM-based relationship extraction |
| `ENABLE_HOT_DOC_DETECTION` | `false` | Sentiment scoring and hot doc flagging |
| `ENABLE_TOPIC_CLUSTERING` | `false` | BERTopic topic clustering |
| `ENABLE_CASE_SETUP_AGENT` | `false` | Case context pre-population |
| `ENABLE_COREFERENCE_RESOLUTION` | `false` | spaCy + coreferee pronoun resolution |
| `ENABLE_GRAPH_CENTRALITY` | `false` | Neo4j GDS centrality metrics |
| `ENABLE_BATCH_EMBEDDINGS` | `false` | Async batch embedding API |
| `ENABLE_REDACTION` | `false` | PII detection and document redaction |
| `ENABLE_SSO` | `false` | OIDC/OAuth2 SSO authentication |
| `ENABLE_SAML` | `false` | SAML 2.0 SSO authentication |
| `ENABLE_GOOGLE_DRIVE` | `false` | Google Drive OAuth connector |
| `ENABLE_MEMO_DRAFTING` | `false` | LLM-powered legal memo generation |
| `ENABLE_DATA_RETENTION` | `false` | Data retention policy enforcement |
| `ENABLE_CHUNK_QUALITY_SCORING` | `false` | Heuristic chunk quality scoring at ingestion |
| `ENABLE_CONTEXTUAL_CHUNKS` | `false` | LLM context prefix enrichment at ingestion |
| `ENABLE_RETRIEVAL_GRADING` | `false` | CRAG-style two-tier retrieval relevance grading |
| `ENABLE_MULTI_QUERY_EXPANSION` | `false` | Multi-query expansion with legal vocabulary variants |
| `ENABLE_TEXT_TO_CYPHER` | `false` | Natural language to Cypher query generation |
| `ENABLE_PROMPT_ROUTING` | `false` | Semantic prompt routing by query type |
| `ENABLE_QUESTION_DECOMPOSITION` | `false` | Explicit question decomposition for complex queries |
| `ENABLE_HYDE` | `false` | Hypothetical Document Embeddings for retrieval |
| `ENABLE_SELF_REFLECTION` | `false` | Self-reflection retry loop after citation verification |
| `ENABLE_TEXT_TO_SQL` | `false` | Matter-scoped natural language to SQL |
| `ENABLE_DOCUMENT_SUMMARIZATION` | `false` | LLM document summarization at ingestion |
| `ENABLE_MULTI_REPRESENTATION` | `false` | Triple RRF fusion (dense + sparse + summary vectors) |
| `ENABLE_PRODUCTION_QUALITY_MONITORING` | `false` | Sampled scoring of retrieval quality |
| `ENABLE_ADAPTIVE_RETRIEVAL_DEPTH` | `false` | Dynamic retrieval depth by query complexity |
| `ENABLE_OCR_CORRECTION` | `false` | LLM-based OCR error correction |
| `ENABLE_DEPOSITION_PREP` | `false` | Deposition prep workflow (witness profiling + questions) |
| `ENABLE_DOCUMENT_COMPARISON` | `false` | Document comparison / redline (difflib side-by-side) |
| `ENABLE_HALLUGRAPH_ALIGNMENT` | `false` | HalluGraph entity-graph post-generation verification |
| `ENABLE_GRAPHRAG_COMMUNITIES` | `false` | GraphRAG community summaries (Louvain + LLM) |
| `ENABLE_SERVICE_OPERATIONS` | `false` | Docker/Celery service management admin UI |
| `ENABLE_AGENT_CLARIFICATION` | `false` | Agent ask_user tool for clarification |
| `ENABLE_AUTO_GRAPH_ROUTING` | `false` | Auto graph routing for entity-rich queries |

## See Also

- [ARCHITECTURE.md](ARCHITECTURE.md) — System design, tech stack, data flow, security model
- [ROADMAP.md](ROADMAP.md) — Milestones, build status, dependency graph
- [CLAUDE.md](CLAUDE.md) — Development conventions and implementation rules
- [docs/modules.md](docs/modules.md) — All 24 domain modules with files, schemas, and endpoints
- [docs/database-schema.md](docs/database-schema.md) — 39 tables, 30 migrations, full column reference
- [docs/feature-flags.md](docs/feature-flags.md) — All 48 feature flags with resource impact
- [docs/agents.md](docs/agents.md) — 6 LangGraph agents with state schemas and tools
- [docs/testing-guide.md](docs/testing-guide.md) — Test infrastructure, fixtures, patterns
- [docs/CLOUD-DEPLOY.md](docs/CLOUD-DEPLOY.md) — Cloud deployment guide (GCP + Vercel)
- [.env.example](.env.example) — All configuration variables
