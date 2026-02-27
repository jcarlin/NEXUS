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
| Frontend | Streamlit (prototype) |

## Prerequisites

- Python 3.12+
- [Docker](https://docs.docker.com/get-docker/) (for infrastructure services)
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- [Anthropic API key](https://console.anthropic.com/)
- [OpenAI API key](https://platform.openai.com/api-keys) (for embeddings)

## Quick Start

1. **Clone and configure environment**

   ```bash
   git clone <repo-url> && cd NEXUS
   cp .env.example .env
   ```

   Edit `.env` and fill in your API keys (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`) and set passwords for Postgres, Neo4j, and MinIO.

2. **Start infrastructure services**

   ```bash
   docker compose up -d
   ```

   This starts Redis, PostgreSQL, Qdrant, Neo4j, and MinIO.

3. **Install Python dependencies**

   ```bash
   uv venv && source .venv/bin/activate
   uv pip install -e ".[dev]"
   ```

4. **Run database migrations**

   ```bash
   alembic upgrade head
   ```

5. **Start the API server**

   ```bash
   uvicorn app.main:app --reload --port 8000
   ```

   API docs available at http://localhost:8000/docs

6. **Start the Celery worker** (separate terminal)

   ```bash
   celery -A workers.celery_app worker -l info
   ```

7. **(Optional) Start the Streamlit frontend** (separate terminal)

   ```bash
   uv pip install -e ".[frontend]"
   streamlit run frontend/app.py
   ```

## Running Tests

```bash
pytest tests/ -v
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
├── frontend/                   # Streamlit dashboard
├── tests/                      # Mirrors app/ structure
├── docker-compose.yml          # Infrastructure services (dev)
├── docker-compose.prod.yml     # Full containerized stack
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
