# NEXUS

Multimodal RAG investigation platform for legal document intelligence. Ingests, analyzes, and queries 50,000+ pages of mixed-format legal documents — surfacing people, relationships, timelines, and patterns across a heterogeneous corpus.

## Tech Stack

| Component | Technology |
|---|---|
| API | FastAPI |
| Task Queue | Celery + Redis |
| Object Storage | MinIO (S3-compatible) |
| Metadata DB | PostgreSQL 16 |
| Vector DB | Qdrant |
| Knowledge Graph | Neo4j |
| LLM | Claude Sonnet 4.5 (Anthropic API) |
| Embeddings | OpenAI `text-embedding-3-large` |
| NER | GLiNER (zero-shot, CPU) |
| Doc Parsing | Docling (PDF, DOCX, XLSX, PPTX, HTML, images) + stdlib (EML, MSG, RTF, CSV, TXT) |
| Query Orchestration | LangGraph (agentic state graph) |
| Structured Output | Instructor |
| Frontend | React 19 + Vite |

## Prerequisites

- Python 3.12+
- Node.js 20+
- [Docker](https://docs.docker.com/get-docker/) (for infrastructure services)
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- [Anthropic API key](https://console.anthropic.com/)
- [OpenAI API key](https://platform.openai.com/api-keys) (for embeddings)
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

## Project Structure

```
nexus/
├── app/
│   ├── main.py                 # FastAPI app factory + lifespan
│   ├── config.py               # Pydantic Settings (all config from env)
│   ├── dependencies.py         # DI: LLM clients, Qdrant, Neo4j, MinIO, Redis
│   ├── auth/                   # JWT auth, RBAC, matter scoping
│   ├── ingestion/              # Upload → parse → chunk → embed → extract → index
│   ├── query/                  # LangGraph agentic query pipeline + chat
│   ├── entities/               # NER, entity resolution, knowledge graph
│   ├── documents/              # Document metadata, preview, download
│   └── common/                 # Shared: middleware, storage, LLM client, vector store
├── workers/
│   └── celery_app.py           # Celery config + task autodiscovery
├── migrations/                 # Alembic migrations
├── frontend/                   # React 19 + Vite dashboard
├── tests/                      # Mirrors app/ structure
├── docker-compose.yml          # Infrastructure services (dev)
├── docker-compose.prod.yml     # Full containerized stack
├── Makefile                    # Dev workflow targets
├── Procfile.dev                # Process definitions for `make dev`
└── pyproject.toml
```

## API Endpoints

Start the server and visit http://localhost:8000/docs for the full interactive OpenAPI documentation.

Key endpoint groups:

- **`/api/v1/ingest`** — Upload and process documents (single, batch, webhook)
- **`/api/v1/query`** — Query the corpus (sync and SSE streaming)
- **`/api/v1/chats`** — Chat thread management
- **`/api/v1/documents`** — Browse, preview, and download documents
- **`/api/v1/entities`** — Entity search and knowledge graph exploration
- **`/api/v1/auth`** — Authentication and user management
- **`/api/v1/health`** — Service health check

## Feature Flags

Optional capabilities controlled via environment variables (all default to `false`):

| Flag | Description |
|---|---|
| `ENABLE_SPARSE_EMBEDDINGS` | BM42 sparse vectors via FastEmbed for hybrid retrieval |
| `ENABLE_RERANKER` | Cross-encoder reranking (`bge-reranker-v2-m3`, runs on MPS/CUDA/CPU) |
| `ENABLE_RELATIONSHIP_EXTRACTION` | LLM-based relationship extraction via Instructor + Claude |
| `ENABLE_VISUAL_EMBEDDINGS` | Visual embeddings for table/figure content (not yet implemented) |

## See Also

- [ARCHITECTURE.md](ARCHITECTURE.md) — System design, security model, data flow
- [ROADMAP.md](ROADMAP.md) — Milestones, build status, dependency graph
- [CLAUDE.md](CLAUDE.md) — Development conventions and implementation rules
- [.env.example](.env.example) — All configuration variables
