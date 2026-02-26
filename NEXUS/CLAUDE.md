# CLAUDE.md — Project Codename: NEXUS
## Multimodal RAG Investigation Platform for Legal Document Intelligence

> **Purpose**: A production-quality, multimodal RAG system for ingesting, analyzing, and querying 50,000+ pages of mixed-format legal documents. Built for investigative intelligence — surfacing people, relationships, timelines, and patterns across a massive heterogeneous corpus.

---

## Build Status

| Milestone | Status | Tests | Summary |
|-----------|--------|-------|---------|
| **M0: Skeleton + Infrastructure** | DONE | 8 | Docker Compose (5 infra services), FastAPI app factory, Alembic migrations (jobs/documents/chat_messages), Celery worker, health checks, stub routers, Pydantic Settings |
| **M1: Single Doc Ingestion** | DONE | 23 | POST /ingest, 6-stage Celery pipeline (parse→chunk→embed→extract→index→complete), Docling parser, semantic chunker, OpenAI embeddings (1024d), GLiNER NER, Qdrant+Neo4j indexing, job tracking |
| **M2: Query Pipeline (LangGraph)** | DONE | 53 | POST /query, POST /query/stream (SSE), LangGraph 8-node state graph (classify→rewrite→retrieve→rerank→check_relevance→graph_lookup→synthesize→follow_ups), HybridRetriever (Qdrant+Neo4j), chat persistence, GET/DELETE /chats |
| **M3: Multi-Format + Entity Resolution** | DONE | 44 | EML/MSG/CSV/RTF parsers (stdlib+extract-msg+striprtf), ZIP extraction with child jobs, batch upload endpoint, email-aware chunking, entity resolution (rapidfuzz+embeddings), feature-flagged relationship extraction (Instructor+Claude), working entity/graph API endpoints |
| **M4: Chat + Streamlit + Doc/Entity Browsing** | DONE | 15 | DocumentService CRUD (raw SQL), 4 working document endpoints (list/get/preview/download with presigned URLs), Streamlit 3-page dashboard (Chat/Documents/Entities), DocumentDetail schema, pyproject frontend optional deps |
| **M5: Production Hardening (Core)** | DONE | 16 | PostgresCheckpointer for multi-turn graph state, streaming refactor (graph.astream + get_stream_writer), MinIO webhook ingestion, Redis sliding-window rate limiting, structlog contextvars (request_id/task_id/job_id), configurable embed batch size |
| **M5b: Production Hardening (Remaining)** | TODO | — | Cross-encoder reranker, Flower monitoring, full test coverage |

**Total tests: 159 passing** (as of M5 core completion)

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        NEXUS Architecture                           │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────┐    ┌──────────────┐    ┌──────────────────────────┐  │
│  │  MinIO    │───▶│ Celery       │───▶│ Parsing Layer            │  │
│  │  (S3)     │    │ Workers      │    │ Docling / Unstructured / │  │
│  │  Bucket   │    │              │    │ PaddleOCR                │  │
│  │  Events   │    └──────┬───────┘    └────────────┬─────────────┘  │
│  └──────────┘           │                          │                │
│                          │    ┌─────────────────────▼──────────┐    │
│                          │    │ Embedding & Indexing            │    │
│                          │    │ BGE-M3 (text) + ColQwen2.5     │    │
│                          │    │ (visual) → Qdrant              │    │
│                          │    └─────────────────────┬──────────┘    │
│                          │                          │               │
│                          │    ┌─────────────────────▼──────────┐    │
│                          │    │ Entity Extraction → KG         │    │
│                          └───▶│ GLiNER + Instructor → Neo4j    │    │
│                               │ (Graphiti)                     │    │
│                               └────────────────────────────────┘    │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                    Query Layer (LangGraph)                    │   │
│  │  User Query → Rewrite → Hybrid Retrieve → Rerank →          │   │
│  │  Graph Lookup → Synthesize → Follow-up Generation            │   │
│  │  (Stateful multi-turn with PostgreSQL checkpointer)          │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                    API Layer (FastAPI)                        │   │
│  │  /ingest, /query, /query/stream, /chat/{id}, /entities,     │   │
│  │  /graph/explore, /jobs/{id}/status, /documents               │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. Technology Stack — Final Decisions

### Core Infrastructure
| Component | Technology | Why This One |
|---|---|---|
| **API Framework** | FastAPI 0.115+ | Async-native, auto OpenAPI docs, dependency injection |
| **Task Queue** | Celery 5.5+ / Redis broker | Persistent tasks, retries, Flower monitoring, worker isolation |
| **Object Storage** | MinIO (S3-compatible) | Self-hosted, bucket event notifications trigger ingestion |
| **Chat/Job Metadata** | PostgreSQL 16 | Chat history, job tracking, user sessions, LangGraph checkpointer |
| **Vector Database** | Qdrant 1.16+ | Native multi-vector (ColPali), hybrid dense+sparse, metadata filtering |
| **Knowledge Graph** | Neo4j 5.x Community + Graphiti | Temporal KG, entity resolution, Cypher queries, LangGraph integration |
| **Cache/Broker** | Redis 7+ | Celery broker, response cache, rate limiting |

### AI Models
| Role | Dev (Cloud API) | Production (Local vLLM) |
|---|---|---|
| **LLM (reasoning)** | Claude Sonnet 4.5 (`claude-sonnet-4-5-20250929`) | Qwen3-235B-A22B or DeepSeek-R1 |
| **LLM (vision)** | Claude Sonnet 4.5 (native vision) | Qwen2.5-VL-72B-Instruct |
| **Text Embeddings** | OpenAI `text-embedding-3-large` OR self-hosted BGE-M3 | BGE-M3 (568M params, MIT) via vLLM/TEI |
| **Visual Retrieval** | ColQwen2.5-v0.2 (self-hosted always) | ColQwen2.5-v0.2 via vLLM |
| **Reranker** | `bge-reranker-v2-m3` | Same, via vLLM/TEI |
| **Zero-shot NER** | GLiNER (DeBERTa, ~600MB) | Same (runs on CPU) |
| **Structured Extract** | Instructor + Claude | Instructor + Qwen3 |

### Document Processing
| File Types | Parser | License |
|---|---|---|
| PDF (native + scanned), DOCX, XLSX, PPTX, HTML, images | **Docling 2.70+** | MIT |
| EML, MSG, RTF, CSV, TXT, legacy DOC | **Unstructured.io 0.18+** | Apache 2.0 |
| Handwritten content, cursive annotations | **PaddleOCR PP-OCRv5** | Apache 2.0 |
| ZIP bundles | Python `zipfile` stdlib → route contents by extension | stdlib |

### Conversation & Orchestration
| Component | Technology | Why |
|---|---|---|
| **Agent Orchestration** | LangGraph 1.x | Stateful graphs, checkpointer memory, tool routing, follow-ups |
| **RAG Retrieval** | LlamaIndex 0.12+ (retrieval only) | Fusion retrievers, query engines, ColPali reranker integration |
| **Structured Output** | Instructor 1.14+ | Pydantic validation, auto-retry, multi-provider support |
| **Conversation Memory** | LangGraph PostgresCheckpointer | Thread-scoped short-term + cross-thread long-term |

---

## 3. Project Structure

```
nexus/
├── CLAUDE.md                          # This file
├── docker-compose.yml                 # All services
├── docker-compose.dev.yml             # Dev overrides
├── .env.example                       # Required env vars
├── pyproject.toml                     # uv/pip, Python 3.12+
│
├── app/
│   ├── __init__.py
│   ├── main.py                        # FastAPI app factory + lifespan
│   ├── config.py                      # Pydantic Settings (all config from env)
│   ├── dependencies.py                # DI: LLM clients, Qdrant, Neo4j, MinIO, Redis
│   │
│   ├── ingestion/                     # Document ingestion domain
│   │   ├── __init__.py
│   │   ├── router.py                  # POST /ingest, POST /ingest/batch, GET /jobs/{id}
│   │   ├── service.py                 # Orchestrates parsing → chunking → embedding → indexing
│   │   ├── tasks.py                   # Celery tasks (long-running background work)
│   │   ├── parser.py                  # Routes files to correct parser (Docling/Unstructured/Paddle)
│   │   ├── chunker.py                 # Semantic chunking with overlap, metadata preservation
│   │   ├── embedder.py                # BGE-M3 + ColQwen2.5 dual embedding
│   │   └── schemas.py                 # Pydantic models: IngestRequest, JobStatus, DocumentMeta
│   │
│   ├── query/                         # Query & chat domain
│   │   ├── __init__.py
│   │   ├── router.py                  # POST /query, POST /query/stream (SSE), GET /chat/{id}
│   │   ├── graph.py                   # LangGraph state graph definition
│   │   ├── nodes.py                   # Graph nodes: rewrite, retrieve, rerank, synthesize, followup
│   │   ├── retriever.py               # Hybrid retrieval: BM25 + dense + ColQwen2.5 → RRF fusion
│   │   ├── prompts.py                 # All prompt templates (system, rewrite, synthesis, followup)
│   │   └── schemas.py                 # QueryRequest, QueryResponse, ChatMessage, SourceDoc
│   │
│   ├── entities/                      # Entity extraction & knowledge graph domain
│   │   ├── __init__.py
│   │   ├── router.py                  # GET /entities, GET /entities/{id}/connections, GET /graph/explore
│   │   ├── extractor.py               # GLiNER + Instructor pipeline
│   │   ├── resolver.py                # Entity resolution (dedup "J. Epstein" / "Jeffrey Epstein")
│   │   ├── graph_service.py           # Neo4j/Graphiti operations, Cypher queries
│   │   └── schemas.py                 # Entity, Relationship, GraphExploreResponse
│   │
│   ├── documents/                     # Document management domain
│   │   ├── __init__.py
│   │   ├── router.py                  # GET /documents, GET /documents/{id}, GET /documents/{id}/preview
│   │   ├── service.py                 # MinIO operations, metadata CRUD
│   │   └── schemas.py                 # Document, DocumentList, DocumentPreview
│   │
│   └── common/                        # Shared utilities
│       ├── __init__.py
│       ├── middleware.py               # CORS, request logging, error handling
│       ├── storage.py                  # MinIO/S3 client wrapper
│       ├── llm.py                      # LLM client factory (Anthropic/OpenAI/vLLM switcher)
│       ├── vector_store.py             # Qdrant client wrapper
│       └── models.py                   # Shared base models
│
├── workers/
│   ├── __init__.py
│   └── celery_app.py                  # Celery configuration, task autodiscovery
│
├── migrations/                        # Alembic for PostgreSQL schema
│   └── ...
│
├── frontend/                          # Minimal React chat UI (optional, can be separate repo)
│   └── ...
│
└── tests/
    ├── test_ingestion/
    ├── test_query/
    ├── test_entities/
    └── conftest.py                    # Fixtures: test Qdrant, test Neo4j, mock LLM
```

---

## 4. Docker Compose Services

```yaml
# docker-compose.yml
services:
  api:
    build: .
    ports: ["8000:8000"]
    env_file: .env
    depends_on: [redis, postgres, qdrant, neo4j, minio]
    volumes:
      - ./app:/app/app  # hot reload in dev

  worker:
    build: .
    command: celery -A workers.celery_app worker -l info -c 4 --max-tasks-per-child=100
    env_file: .env
    depends_on: [redis, postgres, qdrant, neo4j, minio]
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]  # For Docling VLM + ColQwen2.5 + GLiNER

  flower:
    build: .
    command: celery -A workers.celery_app flower --port=5555
    ports: ["5555:5555"]
    depends_on: [redis]

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
    volumes: [redis_data:/data]

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: nexus
      POSTGRES_USER: nexus
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    ports: ["5432:5432"]
    volumes: [postgres_data:/var/lib/postgresql/data]

  qdrant:
    image: qdrant/qdrant:v1.16.3
    ports: ["6333:6333", "6334:6334"]
    volumes: [qdrant_data:/qdrant/storage]
    environment:
      QDRANT__SERVICE__GRPC_PORT: 6334

  neo4j:
    image: neo4j:5-community
    ports: ["7474:7474", "7687:7687"]
    environment:
      NEO4J_AUTH: neo4j/${NEO4J_PASSWORD}
      NEO4J_PLUGINS: '["apoc"]'
    volumes: [neo4j_data:/data]

  minio:
    image: minio/minio
    command: server /data --console-address ":9001"
    ports: ["9000:9000", "9001:9001"]
    environment:
      MINIO_ROOT_USER: ${MINIO_ACCESS_KEY}
      MINIO_ROOT_PASSWORD: ${MINIO_SECRET_KEY}
    volumes: [minio_data:/data]

volumes:
  redis_data:
  postgres_data:
  qdrant_data:
  neo4j_data:
  minio_data:
```

---

## 5. Ingestion Pipeline (Detail)

### 5.1 Flow: Upload → S3 → Event → Celery → Parse → Embed → Index → KG

```python
# The ingestion pipeline is event-driven:
# 1. User uploads files via POST /ingest/batch (or drops into MinIO bucket directly)
# 2. Files are stored in MinIO under: documents/{job_id}/{original_filename}
# 3. A Celery task is dispatched per file (or per batch)
# 4. Each task runs the 5-stage pipeline:

INGESTION_STAGES = [
    "uploading",      # File received, stored in MinIO
    "parsing",        # Docling/Unstructured extracting text + structure
    "chunking",       # Semantic chunking with metadata
    "embedding",      # BGE-M3 text + ColQwen2.5 visual embeddings
    "extracting",     # GLiNER NER + Instructor structured extraction
    "indexing",       # Qdrant upsert + Neo4j graph update
    "complete",       # Done
    "failed",         # Error (with traceback in job metadata)
]
```

### 5.2 Parser Routing Logic

```python
# app/ingestion/parser.py
PARSER_ROUTES = {
    # Docling handles these natively
    ".pdf":  "docling",
    ".docx": "docling",
    ".xlsx": "docling",
    ".pptx": "docling",
    ".html": "docling",
    ".htm":  "docling",
    ".png":  "docling",
    ".jpg":  "docling",
    ".jpeg": "docling",
    ".tiff": "docling",
    ".tif":  "docling",

    # Unstructured handles email + edge formats
    ".eml":  "unstructured",
    ".msg":  "unstructured",
    ".rtf":  "unstructured",
    ".txt":  "unstructured",
    ".csv":  "unstructured",
    ".tsv":  "unstructured",
    ".doc":  "unstructured",  # Legacy Word

    # ZIP: extract and recurse
    ".zip":  "zip_extract",
}

# PaddleOCR is invoked as a SECONDARY pass when:
# 1. Docling OCR confidence score < 0.7 on a page
# 2. Docling detects handwritten content regions
# 3. Explicit handwriting flag set on document
```

### 5.3 Chunking Strategy

```python
# Semantic chunking, NOT fixed-size. Legal documents have natural boundaries.
CHUNKING_CONFIG = {
    "strategy": "semantic",           # Use Docling's document structure
    "max_chunk_tokens": 512,          # ~384 words, fits BGE-M3 well
    "overlap_tokens": 64,             # Sliding overlap for continuity
    "respect_boundaries": True,       # Never split mid-paragraph, mid-table, mid-list
    "metadata_fields": [              # Preserved per chunk
        "source_file",
        "page_number",
        "section_heading",
        "document_type",              # "deposition", "flight_log", "correspondence", etc.
        "date_extracted",             # Any dates found in chunk
        "entities_mentioned",         # Quick NER pass during chunking
    ],
    # Special handling:
    # - Tables → serialize as markdown, keep as single chunk if < max_tokens
    # - Images → store separately, reference via chunk metadata
    # - Email headers → extract To/From/Date/Subject as structured metadata
}
```

### 5.4 Dual Embedding Strategy

```python
# Every document gets TWO types of embeddings:

# 1. TEXT EMBEDDINGS (BGE-M3) — per chunk
#    - Dense vector: 1024 dims (for semantic search)
#    - Sparse vector: variable length (for exact term matching, BM25-like)
#    - Both from single model inference
#    → Stored in Qdrant collection "nexus_text"

# 2. VISUAL EMBEDDINGS (ColQwen2.5-v0.2) — per page image
#    - Multi-vector: ~768 patch embeddings × 128 dims per page
#    - Stored with mean-pooled summary vector for fast initial retrieval
#    - Full patch vectors for MaxSim reranking
#    → Stored in Qdrant collection "nexus_visual"

QDRANT_COLLECTIONS = {
    "nexus_text": {
        "dense_dim": 1024,          # BGE-M3 dense
        "sparse": True,              # BGE-M3 sparse (SPLADE-like)
        "on_disk": False,            # Keep in memory for 50K pages
    },
    "nexus_visual": {
        "multivector_dim": 128,     # ColQwen2.5 patch embeddings
        "max_vectors_per_point": 1024,  # Max patches per page
        "quantization": "binary",    # 2x speed, minimal quality loss
    },
}
```

### 5.5 MinIO Event-Driven Ingestion

```python
# MinIO bucket notification triggers automatic ingestion:
# 1. Configure MinIO webhook for s3:ObjectCreated:* events on "documents" bucket
# 2. Webhook hits POST /ingest/webhook (internal endpoint)
# 3. This creates a Celery task for the new object
# 4. Supports "dump and forget" workflow — drop files into MinIO, walk away

# MinIO bucket structure:
# documents/
#   ├── raw/                    # Original uploaded files (never modified)
#   │   ├── {job_id}/
#   │   │   ├── file1.pdf
#   │   │   └── file2.eml
#   ├── parsed/                 # Extracted text/markdown per file
#   │   ├── {doc_id}.json      # Structured parse output
#   ├── pages/                  # Page images for ColQwen2.5
#   │   ├── {doc_id}/
#   │   │   ├── page_001.png
#   │   │   └── page_002.png
#   └── thumbnails/             # For document preview in chat UI
#       ├── {doc_id}_thumb.png
```

---

## 6. Query Pipeline (LangGraph State Graph)

### 6.1 Conversation State

```python
from typing import TypedDict, Annotated
from langgraph.graph.message import add_messages

class InvestigationState(TypedDict):
    # Conversation
    messages: Annotated[list, add_messages]   # Full chat history
    thread_id: str                             # Conversation thread
    user_id: str                               # For multi-user isolation

    # Current query processing
    original_query: str                        # User's raw question
    rewritten_query: str                       # Optimized for retrieval
    query_type: str                            # "factual" | "analytical" | "exploratory" | "timeline"

    # Retrieved context
    text_results: list[dict]                   # From Qdrant nexus_text
    visual_results: list[dict]                 # From Qdrant nexus_visual
    graph_results: list[dict]                  # From Neo4j graph traversal
    fused_context: list[dict]                  # After RRF fusion + reranking

    # Response
    response: str                              # Generated answer
    source_documents: list[dict]               # Citations with page numbers, file names, MinIO URLs
    follow_up_questions: list[str]             # 3 suggested follow-ups
    entities_mentioned: list[dict]             # Entities found in response (linked to KG)
```

### 6.2 LangGraph Flow

```
START
  │
  ▼
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│ classify     │────▶│ rewrite      │────▶│ retrieve        │
│ query type   │     │ for retrieval│     │ (3-way hybrid)  │
└─────────────┘     └──────────────┘     └────────┬────────┘
                                                   │
                                          ┌────────▼────────┐
                                          │ rerank           │
                                          │ (cross-encoder + │
                                          │  RRF fusion)     │
                                          └────────┬────────┘
                                                   │
                                          ┌────────▼────────┐
                            ┌─────────────│ check_relevance  │──────────────┐
                            │ relevant    └──────────────────┘  not relevant│
                            ▼                                               ▼
                   ┌────────────────┐                              ┌────────────────┐
                   │ graph_lookup   │                              │ reformulate    │
                   │ (Neo4j entity  │                              │ (try different │
                   │  connections)  │                              │  query angles) │
                   └───────┬────────┘                              └────────┬───────┘
                           │                                                │
                           ▼                                                │
                   ┌────────────────┐                                       │
                   │ synthesize     │◀──────────────────────────────────────┘
                   │ (generate      │
                   │  answer +      │
                   │  citations)    │
                   └───────┬────────┘
                           │
                           ▼
                   ┌────────────────┐
                   │ generate       │
                   │ follow_ups     │
                   │ (3 questions)  │
                   └───────┬────────┘
                           │
                           ▼
                         END
```

### 6.3 Key Node Implementations

```python
# --- REWRITE NODE ---
# Resolves pronouns, expands context from chat history
# "What about his flights?" → "What flights did Jeffrey Epstein take according to the flight logs?"

REWRITE_PROMPT = """You are a legal investigation query optimizer.
Given the conversation history and current question, rewrite the question to be:
1. Self-contained (no pronouns referencing chat history)
2. Specific (include full names, dates, locations mentioned in context)
3. Optimized for both keyword search AND semantic similarity

Conversation: {history}
Current question: {question}
Rewritten query:"""


# --- RETRIEVE NODE ---
# Three-way parallel retrieval with RRF fusion
async def retrieve(state: InvestigationState) -> InvestigationState:
    query = state["rewritten_query"]

    # 1. Text retrieval (BGE-M3 dense + sparse hybrid in Qdrant)
    text_results = await qdrant.query(
        collection="nexus_text",
        query_vector=embed_text(query),  # Dense
        sparse_vector=embed_sparse(query),  # Sparse
        limit=20,
        fusion="rrf",
    )

    # 2. Visual retrieval (ColQwen2.5 — searches page images directly)
    visual_results = await qdrant.query(
        collection="nexus_visual",
        query_vector=embed_visual_query(query),  # ColQwen2.5 query encoder
        limit=10,
        search_params={"quantization": {"rescore": True}},  # Binary quant + rescore
    )

    # 3. Graph retrieval (Neo4j — entity-centric)
    entities = extract_entities_from_query(query)  # Quick GLiNER pass
    graph_results = await neo4j.query(
        """
        MATCH (e:Entity)-[r]-(connected)
        WHERE e.name IN $entities
        OPTIONAL MATCH (connected)-[:MENTIONED_IN]->(d:Document)
        RETURN e, r, connected, collect(d) as documents
        LIMIT 20
        """,
        entities=entities,
    )

    return {**state, "text_results": text_results, "visual_results": visual_results, "graph_results": graph_results}


# --- SYNTHESIZE NODE ---
SYNTHESIS_PROMPT = """You are a legal investigation analyst. Answer the question using ONLY the provided evidence.

RULES:
- Cite every claim with [Source: filename, page X]
- Distinguish between facts stated in documents vs. inferences
- Flag contradictions between sources
- Note if evidence is insufficient to fully answer
- Use precise legal/investigative language
- If the query involves a timeline, present events chronologically
- Cross-reference entities across multiple documents when relevant

EVIDENCE:
{context}

KNOWLEDGE GRAPH CONNECTIONS:
{graph_context}

QUESTION: {question}

ANALYSIS:"""


# --- FOLLOW-UP GENERATION NODE ---
FOLLOWUP_PROMPT = """Based on the question asked and the answer provided, generate exactly 3 follow-up
questions that would deepen the investigation. These should:
1. Explore connections to OTHER entities/documents not yet examined
2. Probe for timeline gaps or contradictions
3. Suggest a different analytical angle (financial, geographic, relational)

Question: {question}
Answer: {answer}
Entities found: {entities}

Generate 3 follow-up questions (one per line):"""
```

### 6.4 Chat Features

```python
# Every query response includes:
{
    "response": "Based on flight logs from ...",
    "source_documents": [
        {
            "id": "doc_abc123",
            "filename": "flight_log_2003.pdf",
            "page": 14,
            "chunk_text": "...",           # The actual retrieved passage
            "relevance_score": 0.94,
            "preview_url": "/documents/doc_abc123/preview?page=14",  # Thumbnail
            "download_url": "/documents/doc_abc123/download",
        }
    ],
    "follow_up_questions": [
        "Who else was listed on flights during the same period?",
        "Are there any financial records corresponding to these travel dates?",
        "What depositions reference the locations mentioned in these flight logs?",
    ],
    "entities_mentioned": [
        {"name": "Jeffrey Epstein", "type": "PERSON", "kg_id": "ent_001", "connections": 847},
        {"name": "Lolita Express", "type": "VEHICLE", "kg_id": "ent_042", "connections": 234},
    ],
    "thread_id": "thread_abc",
    "message_id": "msg_xyz",
}

# STREAMING: POST /query/stream returns Server-Sent Events (SSE):
# event: status     data: {"stage": "rewriting"}
# event: sources    data: {"documents": [...]}     ← sent BEFORE generation starts
# event: token      data: {"text": "Based"}
# event: token      data: {"text": " on"}
# event: done       data: {"follow_ups": [...], "entities": [...]}
```

---

## 7. Knowledge Graph Schema (Neo4j)

### 7.1 Node Types

```cypher
// Core entity nodes
(:Person {name, aliases[], first_seen, last_seen, role, description})
(:Organization {name, type, jurisdiction})
(:Location {name, type, address, coordinates})  // type: "residence", "office", "island", "airport"
(:Document {id, filename, type, date, page_count, minio_path})
(:Event {description, date, date_precision, location})
(:Financial {type, amount, currency, date, parties[]})
(:Vehicle {name, type, registration})  // Aircraft, yachts, etc.
(:LegalCase {case_number, court, jurisdiction, filing_date, status})
(:PhoneNumber {number, carrier, owner})
(:EmailAddress {address, owner})

// Chunk reference (links KG back to RAG)
(:Chunk {id, text_preview, page_number, qdrant_point_id})
```

### 7.2 Relationship Types

```cypher
// Person relationships
(Person)-[:ASSOCIATED_WITH {context, since, until, strength}]->(Person)
(Person)-[:EMPLOYED_BY {role, since, until}]->(Organization)
(Person)-[:TRAVELED_TO {date, purpose, companions[]}]->(Location)
(Person)-[:TRAVELED_VIA {date, flight_number, departure, arrival}]->(Vehicle)
(Person)-[:PARTY_TO {role}]->(LegalCase)
(Person)-[:CONTACTED {method, date, frequency}]->(Person)
(Person)-[:OWNS]->(Property|Vehicle|Organization)

// Document relationships
(Entity)-[:MENTIONED_IN {page, context_snippet}]->(Document)
(Document)-[:REFERENCES]->(Document)
(Document)-[:FILED_IN]->(LegalCase)

// Financial relationships
(Person)-[:PAID {amount, date, purpose}]->(Person|Organization)
(Person)-[:RECEIVED_FROM {amount, date, purpose}]->(Person|Organization)

// Temporal
(Event)-[:OCCURRED_AT]->(Location)
(Event)-[:INVOLVED]->(Person)
(Event)-[:EVIDENCED_BY]->(Document)
```

### 7.3 Entity Extraction Pipeline

```python
# Three-tier NER strategy:

# Tier 1: GLiNER (fast, zero-shot, runs on CPU)
GLINER_ENTITY_TYPES = [
    "person", "organization", "location", "date",
    "monetary_amount", "case_number", "court",
    "vehicle", "phone_number", "email_address",
    "flight_number", "address",
]
# Run on every chunk. ~50ms per chunk on CPU.

# Tier 2: Instructor + LLM (slow, high-accuracy, for relationship extraction)
class DocumentRelationships(BaseModel):
    """Extract relationships between entities in this legal document passage."""
    relationships: list[Relationship]

class Relationship(BaseModel):
    source_entity: str
    source_type: str
    target_entity: str
    target_type: str
    relationship_type: str
    context: str          # Brief quote supporting this relationship
    confidence: float     # 0-1
    temporal: str | None  # Date or date range if mentioned
# Run on chunks with 2+ entities detected by Tier 1. ~$0.03-0.10 per chunk.

# Tier 3: Entity Resolution (deduplication)
# "J. Epstein", "Jeffrey Epstein", "Epstein, Jeffrey" → single canonical entity
# Uses: fuzzy string matching (rapidfuzz) + embedding similarity + co-occurrence patterns
# Updates Neo4j with merged entity nodes and alias tracking
```

---

## 8. Configuration (.env)

```bash
# === LLM Providers ===
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...                    # For embeddings (dev mode)
LLM_PROVIDER=anthropic                   # "anthropic" | "openai" | "vllm"
LLM_MODEL=claude-sonnet-4-5-20250929
VLLM_BASE_URL=http://localhost:8080/v1   # For local deployment

# === Embedding ===
EMBEDDING_PROVIDER=openai                # "openai" | "local"
EMBEDDING_MODEL=text-embedding-3-large   # Or "BAAI/bge-m3" for local
COLQWEN_MODEL=vidore/colqwen2.5-v0.2     # Always local (no cloud API)

# === Infrastructure ===
POSTGRES_URL=postgresql://nexus:${POSTGRES_PASSWORD}@postgres:5432/nexus
REDIS_URL=redis://redis:6379/0
QDRANT_URL=http://qdrant:6333
NEO4J_URI=bolt://neo4j:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=changeme

# === MinIO ===
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=nexus-admin
MINIO_SECRET_KEY=changeme
MINIO_BUCKET=documents
MINIO_USE_SSL=false

# === Processing ===
CELERY_CONCURRENCY=4
CHUNK_SIZE=512
CHUNK_OVERLAP=64
GLINER_MODEL=urchade/gliner_multi_pii-v1
PADDLE_OCR_LANG=en
```

---

## 9. API Endpoints

```python
# === Ingestion ===
POST   /api/v1/ingest                    # Single file upload
POST   /api/v1/ingest/batch              # Multi-file upload (accepts ZIP)
POST   /api/v1/ingest/webhook            # MinIO bucket notification handler
GET    /api/v1/jobs/{job_id}             # Job status + progress
GET    /api/v1/jobs                      # List all jobs (paginated)
DELETE /api/v1/jobs/{job_id}             # Cancel running job

# === Query & Chat ===
POST   /api/v1/query                     # Single query (returns full response)
POST   /api/v1/query/stream              # Streaming query (SSE)
GET    /api/v1/chats                     # List chat threads
GET    /api/v1/chats/{thread_id}         # Get full chat history
DELETE /api/v1/chats/{thread_id}         # Delete chat thread

# === Documents ===
GET    /api/v1/documents                 # List ingested documents (filterable)
GET    /api/v1/documents/{doc_id}        # Document metadata + chunks
GET    /api/v1/documents/{doc_id}/preview # Page thumbnail
GET    /api/v1/documents/{doc_id}/download # Original file from MinIO

# === Knowledge Graph ===
GET    /api/v1/entities                  # Search/list entities
GET    /api/v1/entities/{entity_id}      # Entity details + connections
GET    /api/v1/entities/{entity_id}/connections  # Graph neighborhood
GET    /api/v1/graph/explore             # Interactive graph exploration (Cypher)
GET    /api/v1/graph/timeline/{entity}   # Chronological events for entity
GET    /api/v1/graph/stats               # Graph statistics (node/edge counts)

# === System ===
GET    /api/v1/health                    # Health check (all services)
GET    /api/v1/stats                     # Corpus stats (doc count, entity count, etc.)
```

---

## 10. Key Implementation Patterns

### 10.1 LLM Client Abstraction (Cloud ↔ vLLM Swap)

```python
# app/common/llm.py
# The key insight: vLLM exposes an OpenAI-compatible API.
# So cloud→local migration is just changing a URL + model name.

from anthropic import AsyncAnthropic
from openai import AsyncOpenAI  # Used for vLLM too

class LLMClient:
    """Unified LLM client. Swap providers via config, not code."""

    def __init__(self, config: Settings):
        if config.llm_provider == "anthropic":
            self.client = AsyncAnthropic(api_key=config.anthropic_api_key)
        elif config.llm_provider in ("openai", "vllm"):
            self.client = AsyncOpenAI(
                api_key=config.openai_api_key or "not-needed",
                base_url=config.vllm_base_url if config.llm_provider == "vllm" else None,
            )

    async def complete(self, messages, **kwargs) -> str:
        # Unified interface regardless of provider
        ...

    async def stream(self, messages, **kwargs):
        # Yields tokens for SSE streaming
        ...
```

### 10.2 Hybrid Retrieval with RRF Fusion

```python
# app/query/retriever.py
from qdrant_client.models import FusionQuery, Prefetch

async def hybrid_retrieve(query: str, limit: int = 15) -> list[dict]:
    """Three-way retrieval with Reciprocal Rank Fusion."""

    dense_vector = await embed_dense(query)     # BGE-M3 dense
    sparse_vector = await embed_sparse(query)   # BGE-M3 sparse

    # Qdrant handles RRF fusion natively
    results = await qdrant.query_points(
        collection_name="nexus_text",
        prefetch=[
            Prefetch(query=dense_vector, using="dense", limit=30),
            Prefetch(query=sparse_vector, using="sparse", limit=30),
        ],
        query=FusionQuery(fusion="rrf"),
        limit=limit,
        with_payload=True,
    )

    # Separately query visual collection
    visual_results = await qdrant.query_points(
        collection_name="nexus_visual",
        query=await embed_visual_query(query),
        limit=5,
        with_payload=True,
    )

    # Merge text + visual results, deduplicate by document
    return merge_and_deduplicate(results, visual_results)
```

### 10.3 Streaming Response with Source Documents

```python
# app/query/router.py
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse

@router.post("/query/stream")
async def query_stream(request: QueryRequest):
    async def event_generator():
        # Phase 1: Retrieve (send sources immediately)
        yield {"event": "status", "data": json.dumps({"stage": "retrieving"})}

        state = await run_retrieval(request.query, request.thread_id)

        yield {"event": "sources", "data": json.dumps({
            "documents": state["source_documents"]
        })}

        # Phase 2: Stream LLM generation
        yield {"event": "status", "data": json.dumps({"stage": "analyzing"})}

        async for token in llm.stream(build_synthesis_prompt(state)):
            yield {"event": "token", "data": json.dumps({"text": token})}

        # Phase 3: Follow-up questions
        follow_ups = await generate_follow_ups(state)
        yield {"event": "done", "data": json.dumps({
            "follow_ups": follow_ups,
            "entities": state["entities_mentioned"],
        })}

    return EventSourceResponse(event_generator())
```

---

## 11. Development Workflow

### Getting Started
```bash
# 1. Clone and setup
git clone <repo>
cd nexus
cp .env.example .env  # Fill in API keys

# 2. Start infrastructure
docker compose up -d redis postgres qdrant neo4j minio

# 3. Create MinIO bucket
mc alias set nexus http://localhost:9000 nexus-admin changeme
mc mb nexus/documents

# 4. Install Python deps
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"

# 5. Run migrations
alembic upgrade head

# 6. Start API + worker (dev mode)
# Terminal 1:
uvicorn app.main:app --reload --port 8000
# Terminal 2:
celery -A workers.celery_app worker -l info

# 7. Ingest documents (dump into MinIO)
mc cp --recursive /path/to/epstein-docs/ nexus/documents/raw/batch001/
# OR via API:
curl -X POST http://localhost:8000/api/v1/ingest/batch \
  -F "files=@doc1.pdf" -F "files=@doc2.eml" -F "files=@archive.zip"
```

### Testing
```bash
pytest tests/ -v --cov=app
pytest tests/test_ingestion/ -k "test_parser_routing"
pytest tests/test_query/ -k "test_hybrid_retrieval"
```

---

## 12. Production Roadmap (Local vLLM Migration)

```
Phase 1 (Current): Cloud APIs
├── Claude Sonnet 4.5 for reasoning + vision
├── OpenAI text-embedding-3-large for embeddings
├── ColQwen2.5 self-hosted (required, no cloud API)
├── GLiNER self-hosted (CPU, lightweight)
└── All infrastructure in Docker Compose

Phase 2: Hybrid Local
├── Replace OpenAI embeddings → self-hosted BGE-M3 via TEI
├── Add vLLM container for Qwen2.5-VL-72B (vision tasks)
├── Keep Claude for complex reasoning
└── Hardware: 1× A100 80GB or 2× RTX 4090

Phase 3: Fully Local
├── Replace Claude → Qwen3-235B-A22B via vLLM (4-8× A100 80GB)
├── OR → DeepSeek-R1 via vLLM (same hardware)
├── All embeddings, NER, reranking local
├── vLLM OpenAI-compatible API = config change only, no code changes
└── Hardware: 4-8× A100 80GB or equivalent

# The key: vLLM serves an OpenAI-compatible API.
# Migration = change VLLM_BASE_URL + LLM_MODEL in .env. That's it.
```

---

## 13. Future Enhancements (Backlog)

Items under consideration for future milestones. Prioritized by expected impact on investigative query quality.

### 13.1 GraphRAG Community Intelligence (High Priority)

Based on [GraphRAG feasibility research](docs/research/graphrag-feasibility-report.md). NEXUS already has entity extraction, Neo4j KG, and hybrid retrieval — these items add the **community detection and global query** capabilities that the current pipeline lacks.

| # | Enhancement | Description | Effort | Dependencies |
|---|---|---|---|---|
| G1 | **Neo4j GDS community detection** | Run Leiden algorithm on existing entity graph to identify clusters of related entities (e.g., "all people connected to Company X through financial transactions"). No re-indexing needed — operates on entities NEXUS already extracts. | 1 week | `graphdatascience` Python package; verify Neo4j Community Edition GDS support (may need NetworkX fallback) |
| G2 | **LazyGraphRAG query-time summarization** | When a global/corpus-wide query arrives, identify relevant communities via entity matching, extract claims from community members on-the-fly, rank by relevance. Defers LLM cost to query time (99.9% cheaper than full GraphRAG indexing). | 1–2 weeks | G1 (community detection) |
| G3 | **Global query classifier** | Add a "global" query type to the existing LangGraph `classify` node. Routes corpus-wide questions (e.g., "What are the major patterns across all documents?") to community summaries instead of vector retrieval. | 3 days | G2 (query-time summarization) |
| G4 | **Pre-computed community summaries** | For stable/large communities, pre-generate and cache LLM summaries at 2–3 hierarchy levels. Store as nodes in Neo4j linked to constituent entities. Faster than query-time summarization for frequently-queried communities. | 1–2 weeks | G1; optional optimization after G2–G3 prove value |
| G5 | **Community-aware entity explorer** | Surface community structure in the frontend entity browser. Show cluster membership, inter-community bridges, and hierarchical navigation. | 1 week | G1; frontend work |
| G6 | **Incremental community updates** | Re-run community detection on affected subgraphs when new documents are ingested. Invalidate stale community summaries. | 1 week | G1, G4 |

**Key decision:** Do NOT replace the existing ingestion pipeline with Microsoft's `graphrag` library. NEXUS's pipeline is more capable (multi-modal, streaming, entity resolution, cost-efficient GLiNER). Instead, cherry-pick community detection + query-time summarization concepts.

### 13.2 Production Hardening (M5b — Existing)

| # | Enhancement | Description | Effort |
|---|---|---|---|
| P1 | Cross-encoder reranker | `bge-reranker-v2-m3` via TEI for retrieval reranking | 1 week |
| P2 | Flower monitoring | Production Celery monitoring dashboard | 2 days |
| P3 | Full test coverage | Expand from 159 to comprehensive coverage | 2 weeks |

### 13.3 Other Considerations

| # | Enhancement | Description | Priority |
|---|---|---|---|
| O1 | BenchmarkQED evaluation | Adopt Microsoft's automated RAG benchmarking suite to measure retrieval quality regressions | Medium |
| O2 | Personalized PageRank for graph traversal | Research shows graph operators matter more than graph structure — PPR may improve graph retrieval quality | Medium |
| O3 | `neo4j-graphrag` Python package evaluation | Neo4j's official GraphRAG package offers text-to-Cypher, graph traversal retrievers — could complement `graph_service.py` | Low |

---

## 14. Critical Implementation Notes

### DO
- **Stream everything**: SSE for queries, WebSocket for job progress
- **Cite every claim**: Every LLM response must reference source documents with page numbers
- **Deduplicate entities aggressively**: Legal docs repeat names in many forms
- **Batch embedding calls**: Send 32-64 chunks per BGE-M3 inference
- **Use Qdrant's native RRF**: Don't implement fusion in Python
- **Preserve original files**: Never modify uploads in MinIO. Parse outputs go to separate prefix
- **Log everything**: Every query, retrieval, and LLM call → structured logging
- **Retry with backoff**: All LLM API calls get 3 retries with exponential backoff

### DON'T
- **Don't use LangChain**: Use LangGraph for orchestration, LlamaIndex for retrieval primitives, Instructor for structured extraction. LangChain adds unnecessary abstraction layers
- **Don't use pgvector**: It lacks multi-vector (ColPali) support and metadata filtering performance. Use Qdrant
- **Don't use ChromaDB or LanceDB**: No multi-vector support
- **Don't use Marker**: GPL-3.0 license restricts commercial use
- **Don't use fixed-size chunking**: Legal documents have natural structure. Use semantic boundaries
- **Don't store chat history in Redis**: Use PostgreSQL (LangGraph's PostgresCheckpointer). Redis is for cache + broker only
- **Don't call LLM for every NER**: GLiNER handles 90% of entity extraction at 50ms/chunk. Use LLM only for relationship extraction on entity-rich chunks
- **Don't build a custom frontend first**: Use Chainlit or Streamlit for rapid prototyping, then build React UI later

---

## 14. Dependencies (pyproject.toml core)

```toml
[project]
name = "nexus"
requires-python = ">=3.12"
dependencies = [
    # API
    "fastapi>=0.115",
    "uvicorn[standard]",
    "sse-starlette",
    "python-multipart",

    # LLM & AI
    "anthropic>=0.52",
    "openai>=1.60",
    "instructor>=1.14",
    "langchain-core>=0.3",
    "langgraph>=0.4",

    # Document Processing
    "docling>=2.70",
    "unstructured[all-docs]>=0.18",
    "paddleocr>=2.9",
    "paddlepaddle",                  # PaddleOCR backend

    # Embeddings & Retrieval
    "FlagEmbedding",                 # BGE-M3
    "colpali-engine",                # ColQwen2.5
    "llama-index-core",              # Retrieval primitives only

    # Vector DB & Graph
    "qdrant-client>=1.12",
    "neo4j>=5.25",
    "graphiti-core>=0.17",           # Temporal knowledge graph

    # NER
    "gliner>=0.2.24",
    "spacy>=3.8",

    # Infrastructure
    "celery[redis]>=5.5",
    "boto3",                          # MinIO S3 client
    "sqlalchemy>=2.0",
    "alembic",
    "asyncpg",                        # PostgreSQL async driver
    "redis>=5.0",
    "aiofiles",

    # Entity Resolution
    "rapidfuzz",                      # Fuzzy string matching

    # Utilities
    "pydantic>=2.10",
    "pydantic-settings",
    "structlog",                      # Structured logging
    "tenacity",                       # Retry logic
]
```
