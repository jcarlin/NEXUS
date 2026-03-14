# Feature Flags Reference

All 42 feature flags are defined in `app/config.py` (Settings class) and read from environment variables. 39 are registered in `app/feature_flags/registry.py` and toggleable at runtime via the admin UI. All default to `false` unless noted otherwise.

## Runtime Toggling (Admin UI)

Feature flags can be toggled at runtime via the admin UI at `/admin/feature-flags` or the API endpoints below. DB overrides are stored in the `feature_flag_overrides` table and applied to the Settings singleton at startup and on toggle.

### API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/admin/feature-flags` | List all flags with metadata, current state, and override status |
| `PUT` | `/api/v1/admin/feature-flags/{flag_name}` | Toggle a flag (immediate save + apply) |
| `DELETE` | `/api/v1/admin/feature-flags/{flag_name}` | Reset to env default |

All endpoints require `admin` role.

### Risk Levels

Each flag has a risk level that determines the toggle behavior:

| Risk Level | Behavior | Count |
|---|---|---|
| **Safe** | Takes effect immediately, no side effects | 25 flags |
| **Cache Clear** | Clears DI singleton caches, may reload models on next request | 7 flags |
| **Restart Required** | Saved to DB but requires server restart (router/middleware mounts) | 6 flags |

### Celery Caveat

Celery workers run in separate processes with their own Settings singleton. They load DB overrides at worker startup but won't see mid-flight toggle changes until restarted. The admin UI notes this for ingestion-pipeline flags.

## Summary Table

| Flag | Default | Description |
|---|---|---|
| `ENABLE_VISUAL_EMBEDDINGS` | `false` | ColQwen2.5 visual embedding and reranking for PDF pages |
| `ENABLE_SPARSE_EMBEDDINGS` | `false` | BM42 sparse vectors for hybrid dense+sparse retrieval |
| `ENABLE_RERANKER` | **`true`** | Cross-encoder reranking of retrieval results |
| `ENABLE_RELATIONSHIP_EXTRACTION` | `false` | LLM-based relationship extraction via Instructor + Claude |
| `ENABLE_EMAIL_THREADING` | **`true`** | Reconstruct email conversation threads from headers |
| `ENABLE_NEAR_DUPLICATE_DETECTION` | `false` | MinHash-based near-duplicate and version detection |
| `ENABLE_AI_AUDIT_LOGGING` | **`true`** | Log LLM calls and query graph steps to audit tables |
| `ENABLE_BATCH_EMBEDDINGS` | `false` | Async batch embedding API (stub, not yet implemented) |
| `ENABLE_CASE_SETUP_AGENT` | `false` | Pre-populate query context from case/matter metadata |
| `ENABLE_COREFERENCE_RESOLUTION` | `false` | spaCy + coreferee pronoun resolution during entity resolution |
| `ENABLE_GRAPH_CENTRALITY` | `false` | Neo4j GDS centrality metrics (degree, PageRank, betweenness) |
| `ENABLE_HOT_DOC_DETECTION` | `false` | Sentiment/significance scoring to flag key documents |
| `ENABLE_TOPIC_CLUSTERING` | `false` | BERTopic-based topic clustering of document chunks |
| `ENABLE_AGENTIC_PIPELINE` | **`true`** | Agentic LangGraph query pipeline (vs. v1 linear chain) |
| `ENABLE_CITATION_VERIFICATION` | **`true`** | Self-RAG citation verification in query synthesis |
| `ENABLE_AGENT_CLARIFICATION` | `false` | Agent can ask one clarifying question per query when ambiguous |
| `ENABLE_REDACTION` | `false` | PII detection and document redaction engine |
| `ENABLE_GOOGLE_DRIVE` | `false` | Google Drive OAuth connector for document ingestion |
| `ENABLE_CHUNK_QUALITY_SCORING` | `false` | Heuristic chunk quality scoring at ingestion time |
| `ENABLE_CONTEXTUAL_CHUNKS` | `false` | LLM-generated contextual prefixes for chunks |
| `ENABLE_RETRIEVAL_GRADING` | `false` | CRAG-style retrieval relevance grading |
| `ENABLE_PROMETHEUS_METRICS` | `false` | Prometheus metrics endpoint at /metrics |
| `ENABLE_SSO` | `false` | OpenID Connect SSO authentication |
| `ENABLE_MEMO_DRAFTING` | `false` | AI-assisted legal memo drafting |
| `ENABLE_SAML` | `false` | SAML 2.0 SSO authentication (restart required) |
| `ENABLE_MULTI_QUERY_EXPANSION` | `false` | Multi-query reformulation for broader retrieval |
| `ENABLE_TEXT_TO_CYPHER` | `false` | Natural language to Cypher query generation |
| `ENABLE_PROMPT_ROUTING` | `false` | Semantic routing to specialized system prompts |
| `ENABLE_QUESTION_DECOMPOSITION` | `false` | Decompose complex queries into sub-questions |
| `ENABLE_DATA_RETENTION` | `false` | Data retention policy enforcement |
| `ENABLE_HYDE` | `false` | HyDE: embed hypothetical answer for dense retrieval vocabulary bridging |
| `ENABLE_SELF_REFLECTION` | `false` | Re-investigate flagged claims when faithfulness < threshold |
| `ENABLE_TEXT_TO_SQL` | `false` | Natural language to SQL query generation |
| `ENABLE_DOCUMENT_SUMMARIZATION` | `false` | LLM-generated 2-3 sentence document summaries at ingestion |
| `ENABLE_MULTI_REPRESENTATION` | `false` | Chunk summaries as third vector for triple RRF fusion |
| `ENABLE_PRODUCTION_QUALITY_MONITORING` | `false` | Sampled production query quality scoring and alerting |

---

## Flags

### Retrieval & Embedding

#### `ENABLE_VISUAL_EMBEDDINGS`
- **Default**: `false`
- **Module**: `app/ingestion/`, `app/query/`, `app/common/vector_store.py`
- **Config key**: `Settings.enable_visual_embeddings`
- **Description**: Enables ColQwen2.5 visual embeddings for PDF pages. During ingestion, PDF pages are rendered at configurable DPI and embedded with a vision-language model. During retrieval, visual reranking blends visual similarity scores with text-based scores.
- **Resources gated**: `VisualEmbedder` singleton via `get_visual_embedder()` in `app/dependencies.py`. Returns `None` when disabled. The `VectorStoreClient` reads this flag to configure Qdrant collection schema (visual named vector). The `HybridRetriever` receives the visual embedder and skips visual reranking when `None`.
- **Runtime impact**: Loads a 3B-parameter ColQwen2.5 model onto MPS/CUDA/CPU. Significant VRAM/RAM usage (~6-8 GB). Adds PDF page rendering (via DPI setting) and per-page embedding to the ingestion pipeline. Increases ingestion time substantially for PDF documents.
- **Related settings**: `VISUAL_EMBEDDING_MODEL`, `VISUAL_EMBEDDING_DEVICE`, `VISUAL_EMBEDDING_BATCH_SIZE`, `VISUAL_EMBEDDING_DIM`, `VISUAL_RERANK_WEIGHT`, `VISUAL_RERANK_TOP_N`, `VISUAL_PAGE_DPI`

#### `ENABLE_SPARSE_EMBEDDINGS`
- **Default**: `false`
- **Module**: `app/ingestion/`, `app/common/vector_store.py`
- **Config key**: `Settings.enable_sparse_embeddings`
- **Description**: Enables BM42 sparse vector generation via FastEmbed during ingestion. When enabled, each chunk gets both a dense vector and a sparse vector, allowing Qdrant's native RRF fusion to combine dense and sparse retrieval.
- **Resources gated**: `SparseEmbedder` singleton via `get_sparse_embedder()` in `app/dependencies.py`. Returns `None` when disabled. The `VectorStoreClient` reads this flag to configure Qdrant collection schema (sparse named vector). Ingestion tasks instantiate a local `SparseEmbedder` when the flag is set.
- **Runtime impact**: Loads the `Qdrant/bm42-all-minilm-l6-v2-attentions` model (~100 MB) on CPU. Adds sparse vector computation per chunk during ingestion. Modest CPU overhead per batch. Qdrant collections require the sparse vector configured at creation time.
- **Related settings**: `SPARSE_EMBEDDING_MODEL`

#### `ENABLE_RERANKER`
- **Default**: **`true`**
- **Module**: `app/query/`
- **Config key**: `Settings.enable_reranker`
- **Description**: Enables cross-encoder reranking of retrieval results before synthesis. Supports local model inference (bge-reranker-v2-m3) or remote TEI endpoint.
- **Resources gated**: `Reranker` or `TEIReranker` singleton via `get_reranker()` in `app/dependencies.py`. Returns `None` when disabled. The query graph `rerank` node checks the flag and skips reranking when disabled, falling back to score-based sorting.
- **Runtime impact**: Local mode loads the `BAAI/bge-reranker-v2-m3` cross-encoder model on MPS/CUDA/CPU (~1-2 GB). Adds latency per query (scoring all candidate chunks through the cross-encoder). TEI mode offloads compute to a remote server.
- **Related settings**: `RERANKER_MODEL`, `RERANKER_TOP_N`, `RERANKER_PROVIDER` (`local` | `tei`), `TEI_RERANKER_URL`

### Entity & Graph

#### `ENABLE_RELATIONSHIP_EXTRACTION`
- **Default**: `false`
- **Module**: `app/entities/`, `app/ingestion/`
- **Config key**: `Settings.enable_relationship_extraction`
- **Description**: Enables Tier-2 relationship extraction using Instructor + Claude LLM. When enabled, entity-rich chunks are sent to the LLM to extract structured relationships between entities (e.g., employer-employee, attorney-client). Without this flag, only GLiNER NER entities and basic `MENTIONED_IN` edges are created.
- **Resources gated**: No dedicated DI singleton. The ingestion pipeline conditionally calls `_extract_relationships()` in `app/ingestion/tasks.py` and uses the `RelationshipExtractor` in `app/entities/relationship_extractor.py`. Each call consumes LLM API tokens.
- **Runtime impact**: Makes LLM API calls (Anthropic/OpenAI) for each entity-rich chunk during ingestion. Significantly increases ingestion time and cost for large corpora. No local model loading; cost is API-bound.

#### `ENABLE_COREFERENCE_RESOLUTION`
- **Default**: `false`
- **Module**: `app/entities/`
- **Config key**: `Settings.enable_coreference_resolution`
- **Description**: Enables pronoun and noun-phrase coreference resolution using spaCy + coreferee during entity resolution. Resolves "he", "she", "the company" to their antecedent entities for more accurate entity graphs.
- **Resources gated**: `CoreferenceResolver` singleton via `get_coref_resolver()` in `app/dependencies.py`. Returns `None` when disabled. The entity resolution agent (`app/entities/resolution_agent.py`) checks the flag and skips the coreference step when disabled.
- **Runtime impact**: Loads the `en_core_web_lg` spaCy model (~560 MB) plus the coreferee pipeline component. CPU-intensive NLP processing per text chunk. Note: coreferee is listed as an optional dependency in `pyproject.toml` due to installation complexity.
- **Related settings**: `COREFERENCE_MODEL`

#### `ENABLE_GRAPH_CENTRALITY`
- **Default**: `false`
- **Module**: `app/analytics/`, `app/query/tools.py`
- **Config key**: `Settings.enable_graph_centrality`
- **Description**: Enables Neo4j Graph Data Science (GDS) centrality computations (degree, PageRank, betweenness) on the entity knowledge graph. Used by the analytics service and exposed as an agentic tool for the query pipeline.
- **Resources gated**: No dedicated DI singleton. The `AnalyticsService.get_network_centrality()` method delegates to `GraphService.compute_centrality()`. Requires Neo4j GDS plugin installed on the Neo4j server.
- **Runtime impact**: Centrality algorithms run server-side in Neo4j. Computational cost depends on graph size. No additional local model loading. Requires Neo4j GDS plugin (not part of default Neo4j Community).

### Ingestion Pipeline

#### `ENABLE_EMAIL_THREADING`
- **Default**: **`true`**
- **Module**: `app/ingestion/`
- **Config key**: `Settings.enable_email_threading`
- **Description**: Reconstructs email conversation threads from `In-Reply-To` and `References` headers during ingestion. Groups related emails into thread hierarchies stored in PostgreSQL.
- **Resources gated**: No DI singleton. The `EmailThreader` class in `app/ingestion/threading` is lazily imported in the ingestion task when the flag is enabled and the document type is `email`.
- **Runtime impact**: Minimal. Lightweight header parsing and SQL operations. No model loading. Runs as a post-processing step after core ingestion completes.

#### `ENABLE_NEAR_DUPLICATE_DETECTION`
- **Default**: `false`
- **Module**: `app/ingestion/`
- **Config key**: `Settings.enable_near_duplicate_detection`
- **Description**: Detects near-duplicate documents using MinHash locality-sensitive hashing (Jaccard similarity). Also identifies document versions when similarity is above the version threshold. Dispatched as a fire-and-forget Celery task after ingestion.
- **Resources gated**: `NearDuplicateDetector` singleton via `get_dedup_detector()` in `app/dependencies.py`. Returns `None` when disabled. The detector and `VersionDetector` are lazily imported in the `detect_duplicates` Celery task.
- **Runtime impact**: Minimal CPU and memory. MinHash with configurable permutations (~128 by default). Runs asynchronously via Celery, so no impact on ingestion request latency.
- **Related settings**: `DEDUP_JACCARD_THRESHOLD`, `DEDUP_NUM_PERMUTATIONS`, `DEDUP_SHINGLE_SIZE`, `DEDUP_VERSION_UPPER_THRESHOLD`

#### `ENABLE_HOT_DOC_DETECTION`
- **Default**: `false`
- **Module**: `app/ingestion/`, `app/analysis/`
- **Config key**: `Settings.enable_hot_doc_detection`
- **Description**: Scores documents for investigative significance (sentiment, entity density, keyword signals) to flag "hot" documents during ingestion. Dispatched as a fire-and-forget Celery task via `scan_document_sentiment`.
- **Resources gated**: No DI singleton. The `app/analysis/tasks.scan_document_sentiment` task is lazily imported and dispatched only when the flag is enabled.
- **Runtime impact**: Runs asynchronously via Celery. Computational cost depends on the scoring implementation. No impact on ingestion request latency.
- **Related settings**: `HOT_DOC_SCORE_THRESHOLD`

### Query Pipeline

#### `ENABLE_AGENTIC_PIPELINE`
- **Default**: **`true`**
- **Module**: `app/query/`
- **Config key**: `Settings.enable_agentic_pipeline`
- **Description**: Selects the agentic LangGraph query pipeline (tool-use loop with `create_react_agent` subgraph) instead of the v1 9-node linear chain. The agentic pipeline supports iterative retrieval, multi-step reasoning, and dynamic tool selection. When disabled, falls back to the deterministic v1 graph.
- **Resources gated**: `get_query_graph()` in `app/dependencies.py` conditionally imports and compiles either `build_agentic_graph` or `build_graph_v1`. Both share the same checkpointer and retriever singletons. The query router (`app/query/router.py`) and service use this flag to determine state construction and response extraction logic.
- **Runtime impact**: No additional model loading. The agentic pipeline may issue more LLM calls per query (iterative tool-use loop) compared to the single-pass v1 chain. Recursion limits are configurable per tier.
- **Related settings**: `AGENTIC_RECURSION_LIMIT_FAST`, `AGENTIC_RECURSION_LIMIT_STANDARD`, `AGENTIC_RECURSION_LIMIT_DEEP`

#### `ENABLE_CITATION_VERIFICATION`
- **Default**: **`true`**
- **Module**: `app/query/`
- **Config key**: `Settings.enable_citation_verification`
- **Description**: Enables self-RAG citation verification during query synthesis. When enabled, each claim in the LLM response is verified against retrieved source chunks to ensure factual grounding. Skipped for "fast" tier queries regardless of the flag.
- **Resources gated**: No DI singleton. The `case_context_resolve` node in `app/query/nodes.py` reads the flag to decide whether to run verification logic. Verification may consume additional LLM API calls.
- **Runtime impact**: Adds latency to query responses by verifying up to `MAX_CLAIMS_TO_VERIFY` (default 10) claims. Each verification may require an LLM call. No local model loading.
- **Related settings**: `MAX_CLAIMS_TO_VERIFY`

#### `ENABLE_AGENT_CLARIFICATION`
- **Default**: `false`
- **Module**: `app/query/tools.py`, `app/query/graph.py`, `app/query/nodes.py`, `app/query/router.py`
- **Config key**: `Settings.enable_agent_clarification`
- **Description**: Allows the investigation agent to ask the user one clarifying question per query when it encounters genuine ambiguity (multiple entity matches, unclear time ranges, too many results). Uses LangGraph's `interrupt()` primitive to pause the graph, stream the question via SSE, and resume via `POST /query/resume` when the user responds.
- **Resources gated**: No DI singleton. Adds `ask_user` to the agent's tool list and appends `CLARIFICATION_ADDENDUM` to the system prompt. DI caches cleared: `get_query_graph`.
- **Runtime impact**: Minimal — only adds one additional tool binding to the agent. The at-most-one guard ensures the agent can only ask a single question per investigation. No model loading.
- **Related settings**: None

#### `ENABLE_TOPIC_CLUSTERING`
- **Default**: `false`
- **Module**: `app/query/tools.py`
- **Config key**: `Settings.enable_topic_clustering`
- **Description**: Enables BERTopic-based topic clustering as an agentic tool. When enabled, the query pipeline can cluster document chunks by topic to identify thematic patterns. Returns an informational message when disabled.
- **Resources gated**: No DI singleton. BERTopic and its embedding model are used at query time when the tool is invoked. The tool checks the flag and returns an "not enabled" message when disabled.
- **Runtime impact**: BERTopic loads a sentence-transformer model (default `all-MiniLM-L6-v2`, ~80 MB) and runs HDBSCAN clustering. CPU-intensive for large chunk sets. Only triggered when the agentic pipeline selects the topic clustering tool.
- **Related settings**: `BERTOPIC_EMBEDDING_MODEL`, `BERTOPIC_MIN_CLUSTER_SIZE`

### Case Intelligence

#### `ENABLE_CASE_SETUP_AGENT`
- **Default**: `false`
- **Module**: `app/query/`, `app/cases/`
- **Config key**: `Settings.enable_case_setup_agent`
- **Description**: Pre-populates query context from case/matter metadata before query execution. When enabled, the `CaseContextResolver` fetches matter-specific context (key entities, timeline bounds, case summary) and injects it into the query state for better-informed retrieval and synthesis.
- **Resources gated**: No DI singleton. The `CaseContextResolver` in `app/cases/context_resolver` is lazily imported in `QueryService.build_v1_state()` when the flag is enabled.
- **Runtime impact**: Adds a database query to fetch case context before each query invocation. Minimal overhead. No model loading.

### Audit & Compliance

#### `ENABLE_AI_AUDIT_LOGGING`
- **Default**: **`true`**
- **Module**: `app/query/`, `app/common/llm.py`
- **Config key**: `Settings.enable_ai_audit_logging`
- **Description**: Logs all LLM API calls and query graph node executions to the `ai_audit_log` PostgreSQL table. Captures model, token counts, latency, and query metadata for SOC 2 compliance and cost tracking.
- **Resources gated**: No DI singleton. The LLM client (`app/common/llm.py`) checks the flag after each LLM call and writes an audit record. The query graph synthesis node (`app/query/nodes.py`) also logs audit entries when enabled.
- **Runtime impact**: Minimal. One additional SQL INSERT per LLM call. No model loading. Audit records are fire-and-forget (failures are logged but do not block the request).
- **Related settings**: `AUDIT_RETENTION_DAYS`

### Experimental / Stub

#### `ENABLE_BATCH_EMBEDDINGS`
- **Default**: `false`
- **Module**: `app/common/embedder.py` (config only)
- **Config key**: `Settings.enable_batch_embeddings`
- **Description**: Placeholder for async batch embedding API support (e.g., OpenAI batch API). Currently a stub -- the system uses real-time synchronous embedding in all cases. The flag is defined in config but has no runtime gate in the current codebase.
- **Resources gated**: None. No DI singleton or conditional logic references this flag beyond config definition.
- **Runtime impact**: None. Enabling this flag currently has no effect.
- **Related settings**: `BATCH_EMBEDDINGS_POLL_INTERVAL`

#### `ENABLE_REDACTION`
- **Default**: `false`
- **Module**: `app/redaction/`
- **Config key**: `Settings.enable_redaction`
- **Description**: Enables the PII detection and document redaction engine. The redaction module (`app/redaction/`) provides endpoints for detecting PII, suggesting privilege redactions, and applying redactions to PDF documents. The router is always registered in `app/main.py` but the flag signals operational readiness.
- **Resources gated**: No DI singleton. The redaction module uses GLiNER-based PII detection (`app/redaction/pii_detector.py`) and PDF manipulation (`app/redaction/engine.py`). The router is unconditionally mounted; the flag serves as a feature-readiness indicator.
- **Runtime impact**: When the redaction endpoints are called, PII detection runs GLiNER inference and PDF redaction performs page-level manipulation. No startup cost -- resources are loaded on-demand per request.

#### `ENABLE_GOOGLE_DRIVE`
- **Default**: `false`
- **Module**: `app/gdrive/`
- **Config key**: `Settings.enable_google_drive`
- **Description**: Enables the Google Drive OAuth connector for importing documents directly from Drive. Users can connect their Google Drive account via OAuth2, browse files, and ingest them into a matter. Google-native formats (Docs/Sheets/Slides) are exported to PDF. Incremental sync tracks changes by file modification time.
- **Resources gated**: `GDriveService` DI singleton (`app/dependencies.py:get_gdrive_service`). The `gdrive` router is only mounted in `app/main.py` when this flag is `true`. Database tables `google_drive_connections` and `google_drive_sync_state` are created by migration 014 regardless of the flag.
- **Runtime impact**: No startup cost. Google API libraries are imported lazily. OAuth tokens are encrypted at rest with Fernet (requires `GDRIVE_ENCRYPTION_KEY`). File downloads run in Celery tasks.
- **Related settings**: `GDRIVE_CLIENT_ID`, `GDRIVE_CLIENT_SECRET`, `GDRIVE_REDIRECT_URI`, `GDRIVE_ENCRYPTION_KEY`, `GDRIVE_MAX_CONCURRENT_DOWNLOADS`

### Data Quality

#### `ENABLE_CHUNK_QUALITY_SCORING`
- **Default**: `false`
- **Module**: `app/ingestion/`
- **Config key**: `Settings.enable_chunk_quality_scoring`
- **Description**: Enables heuristic quality scoring for each chunk during ingestion. Scores chunks on coherence (sentence structure), information density (substantive vs boilerplate), completeness (truncation detection), and length. The composite `quality_score` (0.0–1.0) is stored in the Qdrant payload for optional query-time filtering.
- **Resources gated**: No DI singleton. The `quality_scorer.score_chunk()` function is called inline in `_stage_chunk()`. Pure Python heuristics — no model loading.
- **Runtime impact**: Negligible (~5ms per chunk). No external calls, no model loading. Adds a `quality_score` field to each Qdrant point payload.

#### `ENABLE_CONTEXTUAL_CHUNKS`
- **Default**: `false`
- **Module**: `app/ingestion/`
- **Config key**: `Settings.enable_contextual_chunks`
- **Description**: Enables LLM-generated contextual prefixes for each chunk during ingestion. An LLM call generates a concise sentence describing each chunk's content and role in the document. The prefix is prepended to the chunk text before embedding (improving retrieval precision) and stored separately in Qdrant for transparency. Citations always show original chunk text.
- **Resources gated**: Uses the existing `LLMClient` (no new DI singleton). Batches chunks (default 20/call) with configurable concurrency (default 4 concurrent batches).
- **Runtime impact**: Adds LLM calls during ingestion (~15-30s per document with Haiku, batched). Cost depends on model: ~$0.00004/chunk with Haiku + batching. Configurable via `CONTEXTUAL_CHUNK_MODEL` (can use local LLM for zero API cost).
- **Related settings**: `CONTEXTUAL_CHUNK_MODEL`, `CONTEXTUAL_CHUNK_MAX_TOKENS`, `CONTEXTUAL_CHUNK_BATCH_SIZE`, `CONTEXTUAL_CHUNK_CONCURRENCY`

#### `ENABLE_RETRIEVAL_GRADING`
- **Default**: `false`
- **Module**: `app/query/`
- **Config key**: `Settings.enable_retrieval_grading`
- **Description**: Enables CRAG-style retrieval relevance grading in the V1 query pipeline. Uses a two-tier approach: (1) fast heuristic scoring of keyword/entity overlap + Qdrant similarity score for all chunks, and (2) conditional LLM grading when the median heuristic score falls below a configurable threshold. Adds a `grade_retrieval` node between `retrieve` and `rerank` in the V1 graph.
- **Resources gated**: No DI singleton. Uses the existing `LLMClient` for Tier 2 grading. Heuristic scoring is pure Python.
- **Runtime impact**: Tier 1 (heuristic): ~10ms. Tier 2 (LLM): +0.5-2s, only triggered for low-confidence retrievals (median score < threshold). High-confidence queries skip LLM grading entirely.
- **Related settings**: `GRADING_MODEL`, `GRADING_CONFIDENCE_THRESHOLD`

### Tier 1 Maturity

#### `ENABLE_MULTI_QUERY_EXPANSION`
- **Default**: `false`
- **Module**: `app/query/`
- **Config key**: `Settings.enable_multi_query_expansion`
- **Description**: Generates 3-5 legal vocabulary reformulations per query for broader retrieval coverage. Addresses legal vocabulary mismatch (e.g., "deal" vs. "transaction" vs. "agreement").
- **Resources gated**: No DI singleton. Checked inline in `vector_search` tool. Uses existing `LLMClient`.
- **Runtime impact**: Adds one LLM call + N parallel retrieval calls per `vector_search` invocation. Increases retrieval latency but improves recall.
- **Related settings**: `MULTI_QUERY_COUNT`

#### `ENABLE_TEXT_TO_CYPHER`
- **Default**: `false`
- **Module**: `app/query/`
- **Config key**: `Settings.enable_text_to_cypher`
- **Description**: Enables a `cypher_query` tool that generates read-only Cypher queries from natural language and executes them against the Neo4j knowledge graph. All queries are validated for safety (read-only, matter-scoped, LIMIT enforced).
- **Resources gated**: No DI singleton. Registered as an agent tool. Uses existing `LLMClient` and `GraphService`.
- **Runtime impact**: Adds an LLM call for Cypher generation + Neo4j query execution (max 10s timeout). Only triggered when the agent selects the tool.

#### `ENABLE_PROMPT_ROUTING`
- **Default**: `false`
- **Module**: `app/query/`
- **Config key**: `Settings.enable_prompt_routing`
- **Description**: Routes queries to specialized system prompt addenda based on query type classification (factual, analytical, exploratory, timeline). Appends type-specific instructions to the base investigation prompt.
- **Resources gated**: No DI singleton. Checked inline in `case_context_resolve` and `build_system_prompt`. Uses one LLM call for classification.
- **Runtime impact**: Adds one LLM classification call in `case_context_resolve`. Negligible added latency.

#### `ENABLE_QUESTION_DECOMPOSITION`
- **Default**: `false`
- **Module**: `app/query/`
- **Config key**: `Settings.enable_question_decomposition`
- **Description**: Provides a `decompose_query` tool that breaks complex multi-part questions into 2-4 independent sub-questions with independent retrieval per sub-question.
- **Resources gated**: No DI singleton. Registered as an agent tool. Uses existing `LLMClient` and `HybridRetriever`.
- **Runtime impact**: Adds one Instructor call for decomposition + parallel retrieval per sub-question. Only triggered when the agent selects the tool.

### Tier 2 Maturity

#### `ENABLE_HYDE`
- **Default**: `false`
- **Module**: `app/query/`
- **Config key**: `Settings.enable_hyde`
- **Description**: Hypothetical Document Embeddings (HyDE). Generates a hypothetical answer passage and embeds it instead of the raw query for dense retrieval. Bridges vocabulary gap between user questions and legal document language. Sparse/BM42 retrieval still uses the raw query for exact term matching.
- **Resources gated**: No DI singleton. Checked inline in `HybridRetriever.retrieve_text()`. Uses existing `LLMClient`.
- **Runtime impact**: Adds one LLM call per retrieval to generate the hypothetical document (~100-200 tokens). Increases retrieval latency by ~0.5-1s.
- **Related settings**: `HYDE_MODEL` (override model, empty = use default LLM)

#### `ENABLE_SELF_REFLECTION`
- **Default**: `false`
- **Module**: `app/query/`
- **Config key**: `Settings.enable_self_reflection`
- **Description**: Self-RAG reflection loop. After citation verification, if faithfulness ratio falls below the configured threshold, routes back to the investigation agent with flagged claims highlighted. Maximum 1 retry to prevent infinite loops.
- **Resources gated**: No DI singleton. Adds a conditional edge and `reflect` node to the agentic query graph.
- **Runtime impact**: When triggered, adds one full agent loop iteration (retrieval + synthesis + verification). Only fires when faithfulness < threshold.
- **Related settings**: `SELF_REFLECTION_FAITHFULNESS_THRESHOLD` (default 0.8), `SELF_REFLECTION_MAX_RETRIES` (default 1)

#### `ENABLE_TEXT_TO_SQL`
- **Default**: `false`
- **Module**: `app/query/`
- **Config key**: `Settings.enable_text_to_sql`
- **Description**: Enables a `structured_query` agent tool that generates read-only SQL queries from natural language against a curated subset of safe tables (documents, entities, annotations, memos, entity_relationships). All queries validated for safety (no writes, matter-scoped, LIMIT enforced, table allowlist).
- **Resources gated**: No DI singleton. Registered as an agent tool. Uses existing `LLMClient` and DB session.
- **Runtime impact**: Adds one LLM call for SQL generation + DB query execution. Only triggered when the agent selects the tool.

#### `ENABLE_DOCUMENT_SUMMARIZATION`
- **Default**: `false`
- **Module**: `app/ingestion/`
- **Config key**: `Settings.enable_document_summarization`
- **Description**: Generates a 2-3 sentence summary per document at ingestion time using the first N chunks. Summaries stored in the `documents.summary` column and exposed via the documents API.
- **Resources gated**: No DI singleton. Called inline in ingestion pipeline after chunking. Uses existing `LLMClient`.
- **Runtime impact**: Adds one LLM call per document during ingestion (~200 tokens output). Negligible per-document overhead.

#### `ENABLE_MULTI_REPRESENTATION`
- **Default**: `false`
- **Module**: `app/ingestion/`, `app/common/vector_store.py`
- **Config key**: `Settings.enable_multi_representation`
- **Description**: Multi-representation indexing. Generates one-sentence chunk summaries and stores them as a third named vector (`"summary"`) in Qdrant alongside dense and sparse vectors. Retrieval uses triple RRF fusion across all three representations. Summaries provide broader semantic match; full chunk text is always returned for precise citations.
- **Resources gated**: `VectorStoreClient` creates the `"summary"` named vector in Qdrant. Chunk summarizer uses existing `LLMClient` with configurable concurrency.
- **Runtime impact**: Adds one LLM call per chunk during ingestion (batched, concurrent). Qdrant collection requires schema migration (handled automatically). Retrieval adds one prefetch query.
- **Related settings**: `MULTI_REPRESENTATION_CONCURRENCY` (default 4)

#### `ENABLE_PRODUCTION_QUALITY_MONITORING`
- **Default**: `false`
- **Module**: `app/query/`
- **Config key**: `Settings.enable_production_quality_monitoring`
- **Description**: Scores sampled production queries for retrieval relevance, generation faithfulness, and citation density. Scores stored in `query_quality_metrics` table and recorded as Prometheus histograms. Alert rules fire on rolling 24h average degradation.
- **Resources gated**: No DI singleton. Fire-and-forget background task after query response.
- **Runtime impact**: Scoring is lightweight (no LLM calls — uses existing retrieval scores and verification results). Only samples a configurable percentage of queries.
- **Related settings**: `QUALITY_MONITORING_SAMPLE_RATE` (default 0.1 = 10%)

### Tier 3 Maturity

#### `ENABLE_ADAPTIVE_RETRIEVAL_DEPTH`
- **Default**: `false`
- **Module**: `app/query/`
- **Config key**: `Settings.enable_adaptive_retrieval_depth`
- **Description**: Query-type-dependent retrieval depth. Factual queries retrieve fewer chunks (15 text, 8 graph), while exploratory queries retrieve more (40 text, 20 graph). Query type determined by the classifier node.
- **Resources gated**: No DI singleton. Checked inline in retrieval logic.
- **Runtime impact**: Adjusts retrieval call parameters. No additional model loading.
- **Related settings**: `RETRIEVAL_DEPTH_FACTUAL_TEXT`, `RETRIEVAL_DEPTH_FACTUAL_GRAPH`, `RETRIEVAL_DEPTH_ANALYTICAL_TEXT`, `RETRIEVAL_DEPTH_ANALYTICAL_GRAPH`, `RETRIEVAL_DEPTH_COMPARATIVE_TEXT`, `RETRIEVAL_DEPTH_COMPARATIVE_GRAPH`, `RETRIEVAL_DEPTH_TEMPORAL_TEXT`, `RETRIEVAL_DEPTH_TEMPORAL_GRAPH`, `RETRIEVAL_DEPTH_PROCEDURAL_TEXT`, `RETRIEVAL_DEPTH_PROCEDURAL_GRAPH`, `RETRIEVAL_DEPTH_EXPLORATORY_TEXT`, `RETRIEVAL_DEPTH_EXPLORATORY_GRAPH`

#### `ENABLE_AUTO_GRAPH_ROUTING`
- **Default**: `false`
- **Module**: `app/query/`
- **Config key**: `Settings.enable_auto_graph_routing`
- **Description**: Automatically routes simple factual queries to the V1 linear graph (faster, cheaper) and complex queries to the agentic graph. When disabled, routing is manual via the API `tier` parameter.
- **Resources gated**: No DI singleton. Checked inline in query router.
- **Runtime impact**: Adds one query classification call. Simple queries execute significantly faster via V1.
- **Related settings**: `AGENTIC_RECURSION_LIMIT_FAST`, `AGENTIC_RECURSION_LIMIT_STANDARD`, `AGENTIC_RECURSION_LIMIT_DEEP`

#### `ENABLE_OCR_CORRECTION`
- **Default**: `false`
- **Module**: `app/ingestion/`
- **Config key**: `Settings.enable_ocr_correction`
- **Description**: Post-OCR cleanup for scanned documents. Applies regex-based ligature fixes (ff→ff, fi→fi, etc.) and legal term corrections. Optional LLM-assisted correction for higher quality (expensive).
- **Resources gated**: No DI singleton. Called inline during ingestion.
- **Runtime impact**: Regex corrections are negligible (~1ms/chunk). LLM correction adds one LLM call per chunk when `OCR_CORRECTION_USE_LLM` is enabled.
- **Related settings**: `OCR_CORRECTION_USE_LLM`

#### `ENABLE_DATA_RETENTION`
- **Default**: `false`
- **Module**: `app/common/`
- **Config key**: `Settings.enable_data_retention`
- **Description**: Configurable per-matter data retention with automated purge after retention period. Law firms have ethical obligations to destroy matter data after retention expires.
- **Resources gated**: No DI singleton. Checked by retention management endpoints and scheduled tasks.
- **Runtime impact**: No impact on request path. Purge operations run as background tasks.

#### `ENABLE_SAML`
- **Default**: `false`
- **Module**: `app/auth/`
- **Config key**: `Settings.enable_saml`
- **Description**: SAML 2.0 SSO authentication for enterprise identity providers (Okta, Azure AD, etc.). Extends the OIDC auth flow with SAML support.
- **Resources gated**: SAML router mounted at startup when enabled.
- **Runtime impact**: No startup cost beyond router registration. SAML assertion processing on auth requests.
- **Related settings**: `SAML_ENTITY_ID`, `SAML_IDP_METADATA_URL`, `SAML_IDP_SSO_URL`, `SAML_IDP_CERT`
