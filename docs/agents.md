# LangGraph Agents Reference

NEXUS uses 5 LangGraph agents (plus a Citation Verifier node within the Investigation Orchestrator) for different tasks. All agents use typed state (`TypedDict`), structured output, and matter-scoped security context.

---

## 1. Investigation Orchestrator (Agentic)

The primary query agent. Receives a user question, autonomously selects and calls tools to gather evidence, then synthesizes a cited answer.

- **Location**: `app/query/graph.py` (`build_agentic_graph()`)
- **State schema**: `AgentState(TypedDict)` in `app/query/graph.py`

  ```
  messages:            Annotated[list[BaseMessage], add_messages]
  thread_id:           str
  user_id:             str
  remaining_steps:     Annotated[int, RemainingStepsManager]
  original_query:      str
  _case_context:       str
  _term_map:           dict[str, str]
  _filters:            dict[str, Any] | None
  _exclude_privilege:  list[str]
  _tier:               str                      # fast / standard / deep
  _skip_verification:  bool
  response:            str
  source_documents:    Annotated[list[dict], _replace]
  cited_claims:        Annotated[list[dict], _replace]
  follow_up_questions: Annotated[list[str], _replace]
  entities_mentioned:  Annotated[list[dict], _replace]
  ```

- **Entry points**:
  - `POST /api/v1/query` (non-streaming) -- `app/query/router.py`
  - `POST /api/v1/query/stream` (SSE streaming) -- `app/query/router.py`
  - Controlled by `ENABLE_AGENTIC_PIPELINE=true` in settings (default: `true`). When `false`, falls back to the v1 fixed-chain graph.

- **Graph nodes** (in execution order):
  1. `case_context_resolve` -- Loads case context for the matter via `CaseContextResolver`. Builds a term map for alias resolution. Classifies the query into a tier (`fast`, `standard`, `deep`) using a lightweight heuristic. Sets `_skip_verification` for fast-tier queries.
  2. `investigation_agent` -- A `create_react_agent` subgraph (LangGraph prebuilt). Uses `ChatAnthropic` with all tools bound. The agent autonomously decides which tools to call, iterates, and produces a final response. Has a `post_model_hook` (`audit_log_hook`) that writes each LLM call to the `ai_audit_log` table.
  3. `verify_citations` -- Citation Verifier (see Agent #2 below).
  4. `generate_follow_ups` -- Generates 3 follow-up investigation questions using the `FOLLOWUP_PROMPT` template.

- **Edge structure**:
  ```
  START -> case_context_resolve -> investigation_agent -> verify_citations
        -> generate_follow_ups -> END
  ```

- **Tools available** (from `INVESTIGATION_TOOLS` in `app/query/tools.py`):
  | Tool | Description |
  |---|---|
  | `vector_search` | Semantic similarity search across document chunks |
  | `graph_query` | Query Neo4j knowledge graph for entity relationships |
  | `temporal_search` | Search documents within a date range (YYYY-MM-DD) |
  | `entity_lookup` | Look up entity by name with alias resolution from case context |
  | `document_retrieval` | Retrieve all chunks for a specific document by ID |
  | `case_context` | Retrieve case-level context: claims, parties, terms, timeline |
  | `sentiment_search` | Search by sentiment dimension score (pressure, concealment, etc.) |
  | `hot_doc_search` | Find hot documents ranked by composite risk score |
  | `context_gap_search` | Find documents with missing context or incomplete communications |
  | `communication_matrix` | Analyze sender-recipient communication patterns |
  | `topic_cluster` | Cluster retrieved documents by topic using BERTopic |
  | `network_analysis` | Compute entity centrality metrics (degree, pagerank, betweenness) |

- **Output format**: `QueryResponse` schema containing:
  - `response` (str) -- The synthesized answer with `[Source: filename, page X]` citations
  - `source_documents` (list of `SourceDocument`)
  - `cited_claims` (list of `CitedClaim` with `verification_status`)
  - `follow_up_questions` (list of str)
  - `entities_mentioned` (list of `EntityMention`)
  - `tier` (str) -- The classified query tier

- **Security**: `_filters` (containing `matter_id`) and `_exclude_privilege` are injected into state by the router based on the authenticated user's role and `X-Matter-ID` header. Tools receive these via `InjectedState` -- the LLM never sees these fields. Non-attorney users have `["privileged", "work_product"]` added to `_exclude_privilege`.

- **Checkpointing**: Compiled with `PostgresCheckpointer` for conversation persistence across turns.

- **System prompt**: Dynamically built by `build_system_prompt()` in `app/query/nodes.py`, which injects case context from `INVESTIGATION_SYSTEM_PROMPT` in `app/query/prompts.py`.

---

## 2. Citation Verifier

A node within the Investigation Orchestrator graph that decomposes the agent's response into atomic claims and independently verifies each one. Uses the Chain-of-Verification (CoVe) pattern.

- **Location**: `app/query/nodes.py` (`verify_citations()`, `_decompose_claims()`, `_verify_single_claim()`)
- **State schema**: Operates on `AgentState` (shared with the Investigation Orchestrator)
- **Entry point**: Invoked automatically as the third node in the agentic graph. Skipped when `_skip_verification=True` (fast-tier queries) or when `ENABLE_CITATION_VERIFICATION=false`.

- **Verification pipeline** (3 stages):
  1. **Decompose** (`_decompose_claims`) -- Sends the response and source evidence to the LLM with `VERIFY_CLAIMS_PROMPT`. The LLM returns a JSON array of atomic claims, each with `claim_text`, `filename`, `page_number`, `excerpt`, and `grounding_score`.
  2. **Retrieve** -- For each claim (up to `MAX_CLAIMS_TO_VERIFY`, default 10), runs an independent `retriever.retrieve_text()` call using the claim text as the query. This produces verification evidence separate from the original retrieval.
  3. **Judge** (`_verify_single_claim`) -- Sends the claim and its independently retrieved evidence to the LLM with `VERIFY_JUDGMENT_PROMPT`. The LLM judges whether the claim is supported. Result is `"verified"`, `"flagged"`, or `"unverified"` (on error).

- **Output**: Populates `cited_claims` in state -- a list of dicts with `claim_text`, `filename`, `page_number`, `excerpt`, `grounding_score`, and `verification_status`.

- **Configuration**:
  - `ENABLE_CITATION_VERIFICATION` (bool, default `true`) -- Master toggle
  - `MAX_CLAIMS_TO_VERIFY` (int, default `10`) -- Cap on claims verified per response

---

## 3. Case Setup Agent

Parses an anchor legal document (complaint) and extracts structured case intelligence: claims, parties, defined terms, and a timeline. Results are persisted to PostgreSQL and Neo4j.

- **Location**: `app/cases/agent.py` (`build_case_setup_graph()`, `create_case_setup_nodes()`)
- **State schema**: `CaseSetupState(TypedDict)` in `app/cases/agent.py`

  ```
  matter_id:           str
  anchor_document_id:  str
  case_context_id:     str
  minio_path:          str
  document_text:       str
  claims:              Annotated[list[dict], _replace]
  parties:             Annotated[list[dict], _replace]
  defined_terms:       Annotated[list[dict], _replace]
  timeline:            Annotated[list[dict], _replace]
  error:               str | None
  ```

- **Entry point**: `POST /api/v1/cases/{matter_id}/setup` in `app/cases/router.py`. Uploads an anchor document (complaint) to MinIO, creates a job record and `case_contexts` row in PostgreSQL, then dispatches the `run_case_setup` Celery task (`app/cases/tasks.py`).

- **Graph nodes** (linear chain):
  1. `parse_anchor_doc` -- Downloads the file from MinIO via boto3 (sync), parses it with `DocumentParser` (Docling/stdlib). Produces `document_text`.
  2. `extract_claims` -- Extracts claims using Instructor + `ExtractedClaimList` response model and `EXTRACT_CLAIMS_PROMPT`.
  3. `extract_parties` -- Extracts parties using Instructor + `ExtractedPartyList` response model and `EXTRACT_PARTIES_PROMPT`.
  4. `extract_defined_terms` -- Extracts defined terms using Instructor + `ExtractedDefinedTermList` response model and `EXTRACT_DEFINED_TERMS_PROMPT`.
  5. `build_timeline` -- Extracts chronological events using Instructor + `ExtractedTimeline` response model and `EXTRACT_TIMELINE_PROMPT`.
  6. `populate_graph` -- Creates Neo4j nodes for parties (`Entity` nodes with `case_party=true`) and `Claim` nodes. Links parties to claims.

- **Edge structure**:
  ```
  START -> parse_anchor_doc -> extract_claims -> extract_parties
        -> extract_defined_terms -> build_timeline -> populate_graph -> END
  ```

- **Output format**: Final state is written to PostgreSQL by `_write_results_to_db()` in `app/cases/tasks.py`:
  - Claims -> `case_claims` table
  - Parties -> `case_parties` table
  - Defined terms -> `case_defined_terms` table
  - Timeline -> `case_contexts.timeline` (JSONB column)
  - Status set to `"draft"` (pending lawyer review)

- **Execution context**: Runs synchronously inside a Celery worker via `graph.invoke()`. Uses `asyncio.run()` for the Neo4j populate step. All LLM calls use sync Instructor (not async).

- **Prompt templates**: Centralized in `app/cases/prompts.py` (`EXTRACT_CLAIMS_PROMPT`, `EXTRACT_PARTIES_PROMPT`, `EXTRACT_DEFINED_TERMS_PROMPT`, `EXTRACT_TIMELINE_PROMPT`).

---

## 4. Hot Doc Scanner

A Celery task pipeline that scores documents for sentiment, hot-doc signals, context gaps, and communication anomalies. Not a LangGraph `StateGraph`, but a multi-stage LLM analysis pipeline dispatched per document.

- **Location**: `app/analysis/tasks.py` (`scan_document_sentiment`)
- **Supporting modules**:
  - `app/analysis/sentiment.py` (`SentimentScorer`) -- Instructor-based sentiment scoring
  - `app/analysis/completeness.py` (`CompletenessAnalyzer`) -- Instructor-based context gap detection
  - `app/analysis/anomaly.py` (`CommunicationBaseline`) -- Statistical anomaly detection (no LLM)

- **Entry point**: Dispatched automatically after document ingestion when `ENABLE_HOT_DOC_DETECTION=true` (from `app/ingestion/tasks.py`). Can also be triggered for an entire matter via `scan_matter_hot_docs` task.

- **Pipeline stages** (within `scan_document_sentiment`):
  1. **Fetch chunks** -- Scrolls Qdrant for all chunks belonging to the document (`doc_id` filter). Sorts by `chunk_index` and concatenates, truncating to 8000 characters.
  2. **Sentiment scoring** -- Calls `SentimentScorer.score_document()` which uses Instructor with `DocumentSentimentResult` response model and `SENTIMENT_SCORING_PROMPT`. Scores 7 sentiment dimensions (positive, negative, pressure, opportunity, rationalization, intent, concealment) plus 3 hot-doc signals (admission_guilt, inappropriate_enthusiasm, deliberate_vagueness). Computes a composite `hot_doc_score`.
  3. **Completeness analysis** (emails only) -- For EML/MSG documents, calls `CompletenessAnalyzer.analyze()` with thread context from sibling documents. Uses `CompletenessResult` response model and `COMPLETENESS_ANALYSIS_PROMPT`. Detects 5 gap types: `missing_attachment`, `prior_conversation`, `forward_reference`, `coded_language`, `unusual_terseness`.
  4. **Anomaly detection** (best-effort) -- If the document has a sender, computes a `PersonBaseline` from all of the sender's documents in the matter, then compares the current document's sentiment dimensions against the baseline. Pure statistical computation (no LLM).
  5. **Persist to PostgreSQL** -- Updates the `documents` table with all sentiment columns, `hot_doc_score`, `context_gap_score`, `context_gaps` (JSONB), and `anomaly_score`.
  6. **Propagate to Qdrant** -- Sets `hot_doc_score` and `anomaly_score` on the document's Qdrant points for downstream filtering.

- **Schemas** (in `app/analysis/schemas.py`):
  - `SentimentDimensions` -- 7 float fields (0.0-1.0)
  - `HotDocSignals` -- 3 float fields (0.0-1.0)
  - `DocumentSentimentResult` -- sentiment + signals + hot_doc_score + summary
  - `ContextGapType` (StrEnum) -- 5 gap types
  - `ContextGap` -- gap_type + evidence + severity
  - `CompletenessResult` -- context_gap_score + gaps + summary
  - `PersonBaseline` -- avg_message_length + message_count + tone_profile
  - `AnomalyResult` -- anomaly_score + deviations

- **Bulk dispatch**: `scan_matter_hot_docs(matter_id)` queries for all unscored documents (`hot_doc_score IS NULL`) in a matter and dispatches individual `scan_document_sentiment` tasks for each.

---

## 5. Entity Resolution Agent

A deterministic post-ingestion pipeline that deduplicates entities, resolves coreferences, merges duplicates, infers organizational hierarchy, and links case-defined terms to graph entities.

- **Location**: `app/entities/resolution_agent.py` (`build_resolution_graph()`, `run_resolution_agent()`)
- **State schema**: `ResolutionState(TypedDict)` in `app/entities/resolution_agent.py`

  ```
  matter_id:                str
  entity_type:              str | None
  entities:                 Annotated[list[dict], _replace]
  fuzzy_matches:            Annotated[list[dict], _replace]
  embedding_matches:        Annotated[list[dict], _replace]
  all_matches:              Annotated[list[dict], _replace]
  merge_groups:             Annotated[list[dict], _replace]
  uncertain_merges:         Annotated[list[dict], _replace]
  merges_performed:         int
  hierarchy_edges_created:  int
  linked_terms:             int
  entity_types_processed:   Annotated[list[str], _replace]
  ```

- **Entry point**: Dispatched as a Celery task `agents.entity_resolution_agent` in `app/entities/tasks.py`. Called via `entity_resolution_agent.delay(matter_id)`. Can also be invoked directly via `run_resolution_agent(matter_id)`.

- **Graph nodes** (linear chain):
  1. `extract` -- Fetches all entities from Neo4j, grouped by type. If `entity_type` is specified, processes only that type; otherwise queries for all distinct entity types.
  2. `deduplicate` -- Runs `EntityResolver.find_fuzzy_matches()` using rapidfuzz. Splits matches into confident (score >= 90) and uncertain (below threshold). Confident matches proceed to merge; uncertain are flagged for review.
  3. `resolve_coreferences` -- Feature-flagged (`ENABLE_COREFERENCE_RESOLUTION`). Currently a placeholder node for future integration with spaCy + coreferee.
  4. `merge` -- Computes transitive merge groups from confident matches using `EntityResolver.compute_merge_groups()` (union-find algorithm). Executes merges in Neo4j via `GraphService.merge_entities()`.
  5. `infer_hierarchy` -- Infers `REPORTS_TO` relationships from email communication patterns using `AnalyticsService.infer_org_hierarchy()`. Creates temporal relationships in Neo4j.
  6. `link_defined_terms` -- Bridges case-defined terms (from the Case Setup Agent) to graph entities via `ALIAS_OF` edges. Fetches terms from `CaseService.get_full_context()` and creates edges via `GraphService.create_alias_edge()`.
  7. `present_uncertain` -- Persists uncertain merge candidates for lawyer review via `GraphService.mark_pending_merge()`. Groups candidates by entity name and writes them to Neo4j for the review UI.

- **Edge structure**:
  ```
  START -> extract -> deduplicate -> resolve_coreferences -> merge
        -> infer_hierarchy -> link_defined_terms -> present_uncertain -> END
  ```

- **Thresholds**:
  - `CONFIDENT_FUZZY_THRESHOLD = 90` -- Auto-merge without review
  - `CONFIDENT_COSINE_THRESHOLD = 0.95` -- Planned for embedding-based matching

- **Output**: Dict with `merges_performed`, `hierarchy_edges_created`, `linked_terms`, `uncertain_merges` (count), `entity_types_processed` (count).

---

## V1 Investigation Graph (Legacy)

The original fixed-chain query graph, retained as a fallback when `ENABLE_AGENTIC_PIPELINE=false`.

- **Location**: `app/query/graph.py` (`build_graph_v1()`)
- **State schema**: `InvestigationState(TypedDict)` in `app/query/graph.py`

  ```
  messages:             list[dict]
  thread_id:            str
  user_id:              str
  original_query:       str
  rewritten_query:      str
  query_type:           str       # factual / analytical / exploratory / timeline
  text_results:         Annotated[list[dict], _replace]
  visual_results:       Annotated[list[dict], _replace]
  graph_results:        Annotated[list[dict], _replace]
  fused_context:        Annotated[list[dict], _replace]
  response:             str
  source_documents:     Annotated[list[dict], _replace]
  follow_up_questions:  Annotated[list[str], _replace]
  entities_mentioned:   Annotated[list[dict], _replace]
  _case_context:        str
  _relevance:           str
  _reformulated:        bool
  _filters:             dict[str, Any] | None
  _exclude_privilege:   list[str]
  ```

- **Graph nodes** (9 nodes):
  1. `classify` -- Classifies query type: factual / analytical / exploratory / timeline
  2. `rewrite` -- Rewrites the query for retrieval (pronoun resolution, context expansion)
  3. `retrieve` -- Runs hybrid retrieval (text via Qdrant + graph via Neo4j) in parallel
  4. `rerank` -- Cross-encoder reranking (if `ENABLE_RERANKER`), then visual reranking (if `ENABLE_VISUAL_EMBEDDINGS`), then score-sort fallback
  5. `check_relevance` -- Checks average score of top 5 results against threshold (0.3)
  6. `graph_lookup` -- Extracts entities from top chunks via GLiNER, fetches their Neo4j connections
  7. `reformulate` -- Reformulates the query if results were irrelevant (one retry)
  8. `synthesize` -- Generates the cited answer using `SYNTHESIS_PROMPT`, with token-by-token SSE streaming
  9. `generate_follow_ups` -- Generates 3 follow-up investigation questions

- **Edge structure** (with conditional routing):
  ```
  START -> classify -> rewrite -> retrieve -> rerank -> check_relevance
                                                        |
                                          relevant: graph_lookup -> synthesize -> generate_follow_ups -> END
                                          not_relevant + not_reformulated: reformulate -> retrieve (loop back)
                                          not_relevant + reformulated: graph_lookup (proceed anyway)
  ```

---

## Common Patterns

### Security Context via InjectedState

All agentic tools use `Annotated[dict, InjectedState]` for their `state` parameter. This injects security-scoped fields (`_filters`, `_exclude_privilege`, `_term_map`, `_dataset_doc_ids`) from graph state without exposing them to the LLM. The LLM sees only the tool's docstring and user-facing parameters.

```python
@tool
async def vector_search(
    query: str,
    limit: int = 20,
    state: Annotated[dict, InjectedState] = {},
) -> str:
    ...
    results = await retriever.retrieve_text(
        query,
        limit=limit,
        filters=state.get("_filters"),           # injected, not LLM-visible
        exclude_privilege_statuses=state.get("_exclude_privilege"),
    )
```

### Tool Registration

Tools are defined as `@tool`-decorated async functions in `app/query/tools.py`. They are collected in the `INVESTIGATION_TOOLS` list and passed to `create_react_agent(tools=INVESTIGATION_TOOLS)`. Each tool is a thin wrapper around an existing service (retriever, graph service, case service, analytics service).

### Structured LLM Output

Non-agentic LLM calls (Case Setup, Hot Doc Scanner, Completeness) use Instructor for structured output. Each defines a Pydantic response model and calls `client.chat.completions.create(response_model=...)`. Instructor handles JSON schema generation, output parsing, and automatic retries on validation failure.

### Error Handling

- **Investigation Orchestrator**: The `audit_log_hook` catches and logs failures without blocking the query. Follow-up generation and entity extraction failures are logged but do not fail the response.
- **Citation Verifier**: Individual claim verification failures set `verification_status="unverified"` rather than failing the entire verification pass. Decomposition failures return an empty claims list.
- **Case Setup Agent**: Failures update both the `jobs` and `case_contexts` tables to `"failed"` status. The Celery task has `max_retries=1`.
- **Hot Doc Scanner**: The Celery task has `max_retries=2` with a 60-second delay. Anomaly detection failures are caught and skipped.
- **Entity Resolution Agent**: Individual merge failures are logged but do not stop the pipeline. Hierarchy edge creation and term linking failures are caught per-item.

### Checkpointing and Persistence

- The Investigation Orchestrator is compiled with `PostgresCheckpointer` for multi-turn conversation persistence. Thread state is keyed by `thread_id` in the graph config.
- All other agents (Case Setup, Entity Resolution) are compiled without a checkpointer -- they run as one-shot pipelines and persist results directly to PostgreSQL and Neo4j.

### Execution Context

| Agent | Runtime | Invocation |
|---|---|---|
| Investigation Orchestrator | Async (FastAPI request) | `graph.ainvoke()` / `graph.astream()` |
| Citation Verifier | Async (within orchestrator graph) | Automatic node execution |
| Case Setup Agent | Sync (Celery worker) | `graph.invoke()` via `run_case_setup.delay()` |
| Hot Doc Scanner | Sync (Celery worker) | `scan_document_sentiment.delay()` |
| Entity Resolution Agent | Async via `asyncio.run()` (Celery worker) | `entity_resolution_agent.delay()` |

### Feature Flags

| Flag | Default | Controls |
|---|---|---|
| `ENABLE_AGENTIC_PIPELINE` | `true` | Agentic orchestrator vs. v1 fixed chain |
| `ENABLE_CITATION_VERIFICATION` | `true` | Citation Verifier node (also skipped for fast-tier) |
| `ENABLE_HOT_DOC_DETECTION` | `false` | Hot Doc Scanner dispatch after ingestion |
| `ENABLE_COREFERENCE_RESOLUTION` | `false` | Coreference node in Entity Resolution |
