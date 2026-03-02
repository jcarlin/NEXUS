# Feature Flags Reference

All feature flags are defined in `app/config.py` (Settings class) and read from environment variables. They are aggregated into a `FeatureFlags` nested model at `Settings.features`. All default to `false` unless noted otherwise.

## Summary Table

| Flag | Default | Description |
|---|---|---|
| `ENABLE_VISUAL_EMBEDDINGS` | `false` | ColQwen2.5 visual embedding and reranking for PDF pages |
| `ENABLE_SPARSE_EMBEDDINGS` | `false` | BM42 sparse vectors for hybrid dense+sparse retrieval |
| `ENABLE_RERANKER` | `false` | Cross-encoder reranking of retrieval results |
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
| `ENABLE_REDACTION` | `false` | PII detection and document redaction engine |

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
- **Default**: `false`
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
