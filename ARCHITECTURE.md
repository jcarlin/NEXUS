# NEXUS — System Architecture

> Multimodal RAG Investigation Platform for Legal Document Intelligence

**Last updated:** 2026-02-26 | **Status:** Authoritative — supersedes all prior design docs

---

## Overview

NEXUS ingests, analyzes, and queries 50,000+ pages of mixed-format legal documents. It surfaces people, relationships, timelines, and patterns across a heterogeneous corpus with cited, auditable answers. Built for the eDiscovery / litigation support vertical where investigators and attorneys need to query massive document collections with full auditability and privilege enforcement.

---

## System Architecture

```
               CLIENT                          API GATEWAY

React SPA ──── HTTPS ──── Nginx/Caddy ──── FastAPI ──── JWT Auth Middleware
 (Vite+TS)      SSE                          |          RBAC + Matter Scoping
                                             |          Audit Log Middleware

               ┌────────────────────── QUERY ENGINE ──────────────────────┐
               │                                                         │
               │  LangGraph Agentic Pipeline                             │
               │  ┌──────────────┐   ┌──────────────────────────┐       │
               │  │ Classify     │──>│ Execute (tool-use loop)  │       │
               │  │ + Plan       │   │ - retrieve_text (hybrid) │       │
               │  └──────────────┘   │ - retrieve_graph_*       │       │
               │                     │ - rerank (cross-encoder) │       │
               │                     │ - decompose              │       │
               │                     └───────────┬──────────────┘       │
               │                      ┌──────────▼──────────┐           │
               │                      │ Assess Sufficiency  │           │
               │                      │ (loop or proceed)   │           │
               │                      └──────────┬──────────┘           │
               │                      ┌──────────▼──────────┐           │
               │                      │ Synthesize + Cite   │           │
               │                      │ (structured output)  │           │
               │                      └─────────────────────┘           │
               └─────────────────────────────────────────────────────────┘

               ┌─────────────────────── DATA LAYER ──────────────────────┐
               │  Qdrant (dense+sparse, native RRF)                      │
               │  Neo4j (entity graph, multi-hop, temporal, path-finding)│
               │  PostgreSQL (users, matters, docs, audit, chat)         │
               │  MinIO (raw files, parsed output, page images)          │
               │  Redis (Celery broker, rate limiting, cache)            │
               └─────────────────────────────────────────────────────────┘

               ┌────────────────── INGESTION PIPELINE ───────────────────┐
               │  MinIO Webhook -> Celery                                │
               │  Parse -> Chunk -> Embed(dense+sparse) -> NER ->       │
               │  -> Resolve Entities -> Index(Qdrant+Neo4j+PG)         │
               └─────────────────────────────────────────────────────────┘
```

---

## Tech Stack

### Infrastructure

| Component | Technology | Notes |
|---|---|---|
| API | FastAPI 0.115+ | Async, OpenAPI docs, DI |
| Task Queue | Celery 5.5+ / Redis | Background ingestion pipeline |
| Object Storage | MinIO (S3-compat) | Bucket webhook triggers ingestion |
| Metadata DB | PostgreSQL 16 | Users, matters, jobs, documents, chat, audit, LangGraph checkpointer |
| Vector DB | Qdrant v1.13.2 | Named dense+sparse vectors, native RRF fusion |
| Knowledge Graph | Neo4j 5.x | Entity graph, multi-hop traversal, path-finding, temporal queries |
| Cache/Broker | Redis 7+ | Celery broker, rate limiting, response cache |

### AI Models

| Role | Current | Planned |
|---|---|---|
| LLM (reasoning) | Claude Sonnet 4.5 via Anthropic API | vLLM self-hosted (M17) |
| Text Embeddings | OpenAI `text-embedding-3-large` (1024d) | Self-hosted BGE-M3 (M17) |
| Sparse Embeddings | **Not yet** — planned: FastEmbed `Qdrant/bm42-all-minilm-l6-v2-attentions` | M8 |
| Zero-shot NER | GLiNER (`gliner_multi_pii-v1`, CPU, ~50ms/chunk) | — |
| Structured Extract | Instructor + Claude (feature-flagged: `ENABLE_RELATIONSHIP_EXTRACTION`) | — |
| Reranker | **Not yet** — planned: `bge-reranker-v2-m3` (MPS) | M5b |
| Visual Embeddings | **Not yet** — planned: ColQwen2.5 (`ENABLE_VISUAL_EMBEDDINGS=false`) | M16 (conditional) |

### Document Processing

| File Types | Parser |
|---|---|
| PDF, DOCX, XLSX, PPTX, HTML, images | Docling 2.70+ |
| EML | Python `email` stdlib |
| MSG | `extract-msg` |
| RTF | `striprtf` |
| CSV, TXT | Python stdlib |
| ZIP | `zipfile` stdlib → route contents by extension |

### Orchestration

| Component | Technology |
|---|---|
| Query orchestration | LangGraph (agentic tool-use loop with PostgresCheckpointer) |
| Retrieval primitives | LlamaIndex (core only) |
| Structured output | Instructor 1.14+ |

---

## Ingestion Pipeline

6-stage Celery pipeline with retry, progress tracking, job cancellation, and child job dispatch.

```
MinIO Webhook ──> Celery Task Chain
                    │
                    ├── 1. Parse (Docling / stdlib by extension)
                    ├── 2. Chunk (semantic, 512 tok, 64 overlap, table-aware)
                    ├── 3. Embed (dense: OpenAI 1024d, sparse: FastEmbed BM42)
                    ├── 4. Extract (GLiNER NER, ~50ms/chunk)
                    ├── 5. Resolve (entity resolution: rapidfuzz + embedding + union-find)
                    └── 6. Index (Qdrant + Neo4j + PostgreSQL)
```

### Key Design Decisions

- **Docling over PyMuPDF**: Structural awareness (headings, tables, lists) enables semantic chunking. PyMuPDF gives flat text.
- **GLiNER over LLM NER**: Zero-shot at 50ms/chunk on CPU. LLM extraction reserved for relationship-rich chunks (feature-flagged).
- **Semantic chunking**: Respects paragraph/table boundaries. 512 tokens, 64 overlap, markdown table protection, email-aware body/quote splitting.
- **Dense + sparse embeddings**: OpenAI for dense vectors, FastEmbed BM42 for sparse. Both stored in Qdrant named vectors for native RRF fusion.

---

## Query Engine — Agentic Pipeline

**The core differentiator.** An adaptive tool-use agent loop that tailors retrieval strategy to query complexity.

### State Graph

```
START -> classify_and_plan -> execute_action -> assess_sufficiency
                                   ^                    |
                                   |                    v
                                   +--- (need_more) ---+
                                                        |
                                                   (sufficient)
                                                        |
                                                        v
                                                   synthesize -> follow_ups -> END

                                                   (no_evidence)
                                                        |
                                                        v
                                                   no_answer -> END
```

### Classification-Driven Strategy

`classify_and_plan` uses structured output (Instructor + Claude) to produce:
- `query_type`: factual | analytical | exploratory | timeline | entity_network | comparison
- `complexity`: simple | moderate | complex
- `strategy`: direct_retrieval | decompose_and_retrieve | entity_chain | temporal_scan
- `sub_queries`: decomposed queries for complex cases
- `max_iterations`: 1 (simple) to 3 (complex) — hard cap prevents runaway loops

| Query Type + Complexity | Strategy | Tools Used | Max Iterations |
|---|---|---|---|
| factual + simple | direct_retrieval | `retrieve_text` only | 1 |
| factual + moderate | direct + graph | `retrieve_text` + `graph_neighbors` | 1 |
| analytical | decompose + retrieve | sub-queries via `retrieve_text`, `rerank` merged | 2 |
| timeline | temporal_scan | `retrieve_text` (date-filtered) + `graph_temporal` | 2 |
| entity_network | entity_chain | `graph_community` + `retrieve_text` for context | 3 |
| exploratory | wide retrieval | multi-query expansion + text + graph | 3 |

### Retrieval Tools

1. **`retrieve_text`** — Dense+sparse hybrid via Qdrant native RRF, matter-scoped, privilege-filtered
2. **`retrieve_graph_neighbors`** — Single-hop entity neighborhood (existing)
3. **`retrieve_graph_path`** — Shortest path between entities (new)
4. **`retrieve_graph_temporal`** — Time-bounded connections (new)
5. **`retrieve_graph_community`** — N-hop entity neighborhood (new)
6. **`rerank`** — Cross-encoder (BGE-reranker-v2-m3, runs on Apple Silicon MPS)
7. **`decompose`** — Break complex query into sub-queries

### Sufficiency Assessment

LLM-based evaluation: "sufficient" | "need_more" | "no_evidence". Replaces naive average-score thresholding.

### Structured Synthesis Output

```python
class CitedClaim(BaseModel):
    claim: str
    source_file: str
    page_number: int | None
    confidence: Literal["stated", "inferred", "uncertain"]

class SynthesisOutput(BaseModel):
    summary: str
    analysis: str  # with inline [1], [2] citations
    claims: list[CitedClaim]
    contradictions: list[str]
    gaps: list[str]
```

---

## Retrieval Architecture

### 1. Dense + Sparse Hybrid (Qdrant Native RRF)

Qdrant `nexus_text` collection with named vectors:

```python
client.create_collection(
    collection_name="nexus_text",
    vectors_config={"dense": VectorParams(size=1024, distance=Distance.COSINE)},
    sparse_vectors_config={"sparse": SparseVectorParams()},
)
```

Sparse vectors generated at ingestion time via FastEmbed (`Qdrant/bm42-all-minilm-l6-v2-attentions`).

Query with native prefetch + RRF:

```python
results = client.query_points(
    collection_name="nexus_text",
    prefetch=[
        Prefetch(query=dense_vector, using="dense", limit=40),
        Prefetch(query=sparse_vector, using="sparse", limit=40),
    ],
    query=FusionQuery(fusion=Fusion.RRF),
    limit=15,
    query_filter=matter_and_privilege_filter,
)
```

### 2. Cross-Encoder Reranking

`app/query/reranker.py` with BGE-reranker-v2-m3:
- Runs on Apple Silicon MPS (~50-100ms for 20 docs)
- Re-scores top-40 hybrid results → top-10
- Behind `ENABLE_RERANKER` feature flag

### 3. Query Expansion

For analytical/exploratory queries: generate 3 alternative formulations, retrieve independently, merge + dedup by chunk ID, then rerank the unified set.

### 4. Graph Retrieval

Neo4j traversals augment text retrieval:
- **Single-hop neighbors**: immediate entity connections (existing)
- **Multi-hop BFS**: `get_entity_neighborhood(name, hops=2)` (new)
- **Path finding**: `find_path(entity_a, entity_b, max_hops=5)` (new)
- **Temporal queries**: `get_temporal_connections(name, date_from, date_to)` (new)
- **Co-occurrence**: `compute_co_occurrences(matter_id, min_count=3)` (new, batch)

---

## Knowledge Graph

### Node Types

| Label | Key Properties |
|---|---|
| `:Entity` | id, name, type, aliases, mention_count, matter_id |
| `:Document` | id, filename, file_type, date, matter_id |
| `:Event` | id, description, date, location, participants, matter_id |

### Edge Types

| Relationship | Between | Properties |
|---|---|---|
| `MENTIONED_IN` | Entity → Document | chunk_id, page, context |
| `RELATED_TO` | Entity → Entity | type, description, date_from, date_to, documents |
| `PARTICIPATED_IN` | Entity → Event | role |
| `CO_OCCURS_WITH` | Entity → Entity | frequency, documents |
| `ALIAS_OF` | Entity → Entity | (from resolution) |

### Entity Resolution

- **Pairwise matching**: rapidfuzz (threshold 85) + embedding cosine (>0.92)
- **Transitive closure**: Union-find (disjoint set) — A≈B and B≈C correctly merges A↔B↔C
- **Canonical entity**: Each group merges into one node; aliases preserved

---

## Security Model

### Authentication (`app/auth/` module)

- JWT access tokens (30-min expiry) with `user_id`, `role`, `matter_ids`
- Refresh tokens (7-day, stored hashed in PostgreSQL)
- `python-jose` for JWT, `passlib` + bcrypt for passwords
- API key alternative for programmatic access

### RBAC (4 roles)

| Role | Ingest | Query | View Privileged | Tag Privilege | Manage Users | Audit Log |
|---|---|---|---|---|---|---|
| admin | Yes | Yes | Yes | Yes | Yes | Yes |
| attorney | Yes | Yes | Yes | Yes | No | Own |
| paralegal | Yes | Yes | No | No | No | Own |
| reviewer | No | Yes | No | No | No | No |

### Multi-Tenancy (Case Matters)

- `case_matters` table, `user_case_matters` join table
- `matter_id` FK on jobs, documents, chat_messages
- `X-Matter-ID` header required on all data endpoints
- Qdrant payloads include `matter_id`; queries filter on it
- Neo4j Document and Entity nodes get `matter_id` property

### Privilege Enforcement

- `privilege_status` column on documents: `not_reviewed` | `privileged` | `work_product` | `confidential` | `not_privileged`
- Enforced at the **data layer**: Qdrant filter, SQL WHERE, Neo4j Cypher
- Non-attorney users never see privileged docs — even if frontend filtering fails

### Audit Logging

- Middleware intercepts every API call → `audit_log` table
- Captures: user, action, resource, matter, IP, user_agent, response status
- `GET /admin/audit-log` endpoint (admin-only, filterable)

---

## Data Model

### PostgreSQL Tables

```
Core:       users, roles, case_matters, user_case_matters
Documents:  jobs, documents, chat_messages
Security:   audit_log
Future:     annotations
```

### Qdrant Collections

| Collection | Vectors | Purpose |
|---|---|---|
| `nexus_text` | dense (1024d, cosine) + sparse (BM42) | Text chunk retrieval with native RRF |
| `nexus_visual` | multi-vector (128d, binary quantized) | Page-image retrieval (future, ColQwen2.5) |

Payloads include: `document_id`, `matter_id`, `privilege_status`, `file_type`, `date`, `page_number`, `chunk_text`

### Neo4j Graph

Entity nodes, Document nodes, Event nodes, with relationships as described in the Knowledge Graph section above.

### MinIO Buckets

| Prefix | Content |
|---|---|
| `documents/raw/` | Original uploaded files |
| `documents/parsed/` | Docling/stdlib parse output |
| `documents/pages/` | Page images for visual embeddings (future) |

---

## API Endpoints

```
# Authentication (M6)
POST   /api/v1/auth/login               # JWT token issuance
POST   /api/v1/auth/refresh             # Token refresh
GET    /api/v1/auth/me                  # Current user profile

# Ingestion
POST   /api/v1/ingest                   # Single file upload
POST   /api/v1/ingest/batch             # Multi-file upload (accepts ZIP)
POST   /api/v1/ingest/webhook           # MinIO bucket notification handler
GET    /api/v1/jobs/{job_id}            # Job status + progress
GET    /api/v1/jobs                     # List all jobs (paginated)

# Query & Chat
POST   /api/v1/query                    # Synchronous query (full response)
POST   /api/v1/query/stream             # SSE streaming query
GET    /api/v1/chats                    # List chat threads
GET    /api/v1/chats/{thread_id}        # Full chat history
DELETE /api/v1/chats/{thread_id}        # Delete chat thread

# Documents
GET    /api/v1/documents                # List documents (filterable)
GET    /api/v1/documents/{id}           # Document metadata + chunks
GET    /api/v1/documents/{id}/preview   # Page thumbnail (presigned URL)
GET    /api/v1/documents/{id}/download  # Original file (presigned URL)
PATCH  /api/v1/documents/{id}/privilege # Privilege tagging (M7)

# Knowledge Graph
GET    /api/v1/entities                 # Search/list entities
GET    /api/v1/entities/{id}            # Entity details + connections
GET    /api/v1/entities/{id}/connections # Graph neighborhood
GET    /api/v1/graph/explore            # Graph exploration (Cypher)
GET    /api/v1/graph/stats              # Graph statistics

# Admin (M6+)
GET    /api/v1/admin/audit-log          # Filterable audit log (admin-only)
GET    /api/v1/admin/users              # User management (admin-only)
POST   /api/v1/admin/users              # Create user (admin-only)

# System
GET    /api/v1/health                   # Health check (all services)
```

---

## Key Patterns

- **LLM abstraction** (`app/common/llm.py`): Unified client for Anthropic/OpenAI/vLLM. Cloud→local migration = change `LLM_PROVIDER` + `VLLM_BASE_URL` in `.env`
- **DI singletons** (`app/dependencies.py`): All clients (LLM, Qdrant, Neo4j, MinIO, Redis) via `@lru_cache` factory functions
- **Hybrid retrieval** (`app/query/retriever.py`): Qdrant dense+sparse with native RRF fusion + Neo4j graph traversal
- **SSE streaming** (`app/query/router.py`): Sources sent before generation starts, then token-by-token LLM streaming via `graph.astream` + `get_stream_writer`
- **Structured logging**: `structlog` with contextvars (`request_id`, `task_id`, `job_id`)
- **Feature flags**: `ENABLE_VISUAL_EMBEDDINGS`, `ENABLE_RELATIONSHIP_EXTRACTION`, `ENABLE_RERANKER` (all `false` by default)
- **Raw SQL over ORM**: `sqlalchemy.text()` queries. Clean, performant, appropriate for known query patterns.
- **Privilege at data layer**: Qdrant filter + SQL WHERE + Neo4j Cypher — never API-layer-only filtering.

---

## Decisions Log

### Keep (validated by implementation)
- **Docling** for parsing — structural awareness > flat text extraction
- **GLiNER** for NER — fast, CPU, zero-shot, right for ingestion-time
- **Celery** for ingestion — mature 6-stage pipeline with retry, don't rewrite
- **LangGraph** for orchestration — right abstraction (topology redesigned to agentic loop)
- **Neo4j** for graph — multi-hop/path-finding requires a real graph DB, not PG relations
- **Qdrant** for vectors — native RRF, multi-vector, metadata filtering > pgvector
- **Raw SQL** over ORM — known queries, performance matters

### Changed (from prior implementation)
- Qdrant collection → named dense + sparse vectors with native RRF
- Query pipeline → agentic tool-use loop (classify → execute → assess → synthesize)
- Synthesis output → structured `CitedClaim` objects
- CORS → restricted origins (was `allow_origins=["*"]`)
- Entity resolution → transitive closure via union-find (was pairwise only)
- Graph traversal → multi-hop, temporal, path-finding (was single-hop only)

### Added (not in prior implementation)
- `app/auth/` module (JWT, RBAC, API keys, matter scoping)
- `app/query/reranker.py` (cross-encoder BGE-reranker-v2-m3)
- Sparse embedding in ingestion pipeline (FastEmbed BM42)
- Audit logging middleware
- `evaluation/` directory (ground-truth, metrics, regression tests)
- React frontend (replaces Streamlit prototype)
- Export pipeline (court-ready document packages)

### Avoided (explicitly rejected)
- **Don't remove Neo4j** — multi-hop traversal requires a graph DB
- **Don't use LangChain** — LangGraph + Instructor + direct clients is correct
- **Don't use pgvector** — Qdrant handles multi-vector and native fusion
- **Don't use Marker** — GPL-3.0 license
- **Don't pursue visual embeddings early** — gate on evaluation evidence (M16)
- **Don't over-engineer agentic loop** — 3 iterations max, converge quickly
- **Don't implement full GraphRAG community summarization** — multi-hop traversal gives 90% of value

---

## Configuration

All configuration via environment variables. See `.env.example` for the complete list.

Key feature flags:
- `ENABLE_SPARSE_EMBEDDINGS` — BM42 sparse vectors for hybrid RRF (default: `false`)
- `ENABLE_RERANKER` — Cross-encoder reranking (default: `false`)
- `ENABLE_RELATIONSHIP_EXTRACTION` — LLM relationship extraction (default: `false`)
- `ENABLE_VISUAL_EMBEDDINGS` — ColQwen2.5 page embeddings (default: `false`)
- `ENABLE_SPARSE_EMBEDDINGS` — BM42 sparse vectors (default: `false`)

---

## Development

```bash
# Start infrastructure
docker compose up -d

# Install Python deps
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"

# Run migrations
alembic upgrade head

# Start API (terminal 1)
uvicorn app.main:app --reload --port 8000

# Start Celery worker (terminal 2)
celery -A workers.celery_app worker -l info

# Run tests
pytest tests/ -v --cov=app
```

---

## See Also

- `CLAUDE.md` — Implementation rules, project structure, do/don't guidelines
- `ROADMAP.md` — Milestone tracker with status and dependencies
- `.env.example` — All configuration variables and feature flags
- `docs/CLOUD-DEPLOY.md` — Cloud deployment guide (GCP + Vercel)
- `docs/M6-BULK-IMPORT.md` — Bulk import spec for pre-OCR'd datasets
- `docs/archive/` — Superseded design documents
