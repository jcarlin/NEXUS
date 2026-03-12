# NEXUS RAG Maturity Audit

## Context

This audit evaluates NEXUS's RAG architecture against 2025/2026 state-of-the-art, benchmarked across 8 dimensions. NEXUS is a legal document intelligence platform handling 50k+ pages of mixed-format legal documents with 6 autonomous LangGraph agents, hybrid retrieval, and knowledge graph integration. The focus is on **ingestion pipeline quality** and **data quality** as the highest-leverage improvement areas.

Research sources: 60+ papers, benchmarks, and industry reports (arXiv, MTEB, Stanford, Anthropic, Microsoft Research, Qdrant, LangChain, ACM, Harvard JOLT). Full research with links saved at `docs/RAG-RESEARCH-2026.md`.

---

## Overall Maturity Score: 7.5 / 10

NEXUS is a **mature, production-grade** RAG system that already implements many 2025/2026 best practices. The architecture is sound and extensible. The gaps are primarily in **data enrichment at ingestion time** and **retrieval quality validation** — both high-leverage, moderate-effort improvements.

---

## Dimension Scores

| # | Dimension | Score | Verdict |
|---|-----------|-------|---------|
| 1 | Document Parsing | **9/10** | Excellent |
| 2 | Chunking Strategy | **7/10** | Good — missing contextual enrichment |
| 3 | Embedding Pipeline | **8/10** | Strong — multi-provider, multi-vector |
| 4 | Data Quality & Enrichment | **5/10** | Biggest gap — no chunk quality scoring, no contextual prefixes |
| 5 | Hybrid Retrieval & Reranking | **7/10** | Architecture right, reranking underutilized |
| 6 | Query Orchestration (Agentic) | **9/10** | Industry-leading |
| 7 | Citation & Faithfulness | **8/10** | Strong — extend with confidence scoring |
| 8 | Evaluation & Observability | **6/10** | Framework exists, not yet operationalized |

---

## Dimension 1: Document Parsing — 9/10

### What NEXUS does well
- **Docling** as primary parser — top performer in 2025 benchmarks (97.9% table extraction accuracy, 1.26 sec/page)
- **6 format-specific parsers**: PDF/DOCX/XLSX/PPTX/HTML (Docling), EML/MSG (email), CSV/TSV, RTF, plaintext, ZIP
- **Email-aware parsing**: RFC 5322 threading headers, attachment extraction, child job spawning
- **Visual page rendering**: PDF pages at configurable DPI (144) stored in MinIO for visual embedding
- **Metadata preservation**: Document-level (format, title, author, dates, content hash) + email-specific (subject, from/to/cc/bcc, message-id, in-reply-to)

### Gap
- **OCR error correction**: No post-processing to fix common OCR artifacts. For scanned legal documents, OCR errors directly degrade chunk quality and entity extraction accuracy. Tools like `textacy` or LLM-based correction could clean OCR output before chunking.

### Recommendation
- Low priority. Parsing is already best-in-class. Consider OCR correction only if scanned document quality is a known issue in the corpus.

---

## Dimension 2: Chunking Strategy — 7/10

### What NEXUS does well
- **Semantic block splitting**: Paragraphs and markdown tables as atomic units (not arbitrary byte offsets)
- **Token-bounded**: 512 tokens max via `cl100k_base` tiktoken with 64-token overlap
- **Table preservation**: Markdown tables kept intact, not split mid-row
- **Email-aware**: Body vs. quoted reply sections split and tagged separately
- **Graceful degradation**: Oversized blocks split at sentence boundaries, then word boundaries

### Gaps

#### 1. No contextual enrichment (Anthropic-style contextual retrieval)
**Impact: HIGH.** This is the single highest-leverage improvement available.

Anthropic's research shows prepending an LLM-generated context sentence to each chunk reduces retrieval failures by **49-67%**. The chunk "Revenue grew 3% in Q3" becomes "This chunk is from Acme Corp's Q3 2024 earnings report, North American operations section. Revenue grew 3% in Q3."

The LLM cost is paid **once at ingestion** — no query-time overhead. With prompt caching (Anthropic supports this), the full document is cached and only the per-chunk suffix varies, making this cost-efficient even at 50k pages.

**Current state**: Chunks are embedded with their raw text only. A chunk from page 47 of a 200-page deposition has no context about which witness, which topic, or which time period is being discussed.

#### 2. No parent-child chunk hierarchy
**Impact: MEDIUM.** Currently, retrieval returns individual 512-token chunks. For complex legal questions, the LLM often needs the surrounding context (the full section, the preceding Q&A exchange in a deposition). Parent-child indexing stores fine-grained child chunks (256 tokens) for precise matching and larger parent chunks (1024-2048 tokens) for rich context injection.

#### 3. No chunk quality scoring
See Dimension 4 below.

### Recommendations
1. **Contextual retrieval** — Add an ingestion stage between CHUNKING and EMBEDDING that calls an LLM to generate a context prefix for each chunk. Template: "Given this document [{title}, {type}, {date}], situate this chunk in context." Store the prefix in the chunk text before embedding. Estimated improvement: **49-67% fewer retrieval failures**.
   - Files to modify: `app/ingestion/tasks.py` (new stage), new `app/ingestion/contextualizer.py`
   - Use `app/common/llm.py` client with prompt caching
   - Feature-flag: `ENABLE_CONTEXTUAL_CHUNKS`

2. **Parent-child indexing** — Lower priority. Can be deferred until contextual retrieval is evaluated. Would require changes to `app/ingestion/chunker.py` (dual-level chunking) and `app/common/vector_store.py` (parent lookup by payload).

---

## Dimension 3: Embedding Pipeline — 8/10

### What NEXUS does well
- **5 embedding providers** via `EmbeddingProvider` protocol: OpenAI, Local (BGE), Ollama, TEI, Gemini
- **Dense + sparse multi-vector**: Named vectors in Qdrant (`dense` + `sparse`), native RRF fusion
- **Visual embeddings**: ColQwen2.5 (128d per-token multi-vector, MaxSim) for complex pages — feature-flagged
- **Batch processing**: Configurable batch size (default 32), retry with backoff
- **Audit logging**: Every embedding call logged with SHA-256 hash and metrics
- **Provider switching**: Change `EMBEDDING_PROVIDER` in `.env` — no code changes

### Gaps

#### 1. No Matryoshka dimensionality optimization
OpenAI's `text-embedding-3-large` supports Matryoshka embeddings — you can use 256 dimensions instead of 3072 with <1.5% accuracy loss. NEXUS uses 1024 dimensions, which is already a good balance, but Matryoshka could enable tiered retrieval (fast 256d first pass, full-dim reranking).

#### 2. BM42 sparse model is suboptimal
The current sparse model (`Qdrant/bm42-all-minilm-l6-v2-attentions`) is a basic attention-weighted term frequency model. **SPLADE** (Sparse Lexical And Expansion) learns to expand queries with semantically related terms that don't appear in the query text. This is critical for legal text where vocabulary mismatch is endemic ("termination" vs. "dismissal" vs. "firing" vs. "let go").

#### 3. No unified dense+sparse model
BGE-M3 produces both dense and sparse vectors from a single model pass, eliminating the need for separate sparse encoding. This simplifies the pipeline and ensures dense/sparse representations are semantically aligned.

### Recommendations
1. **Evaluate SPLADE replacement for BM42** — SPLADE's learned query expansion is specifically valuable for legal vocabulary mismatch. Self-hosted, no API dependency. Medium effort.
2. **Evaluate BGE-M3 as unified model** — If moving to a self-hosted embedding model, BGE-M3 eliminates the separate sparse encoding step. 8192 token context supports longer chunks.
3. **Matryoshka optimization** — Low priority unless storage/latency becomes a concern. Current 1024d is a reasonable operating point.

---

## Dimension 4: Data Quality & Enrichment — 5/10 (Biggest Gap)

### What NEXUS does well
- **Near-duplicate detection**: MinHash + LSH (Jaccard 0.80, 128 permutations) — feature-flagged
- **Version detection**: Filename pattern matching for document versions
- **Content hash**: SHA-256 for bit-identical re-upload detection
- **Entity extraction**: GLiNER with 12 entity types, within-document dedup
- **Matter-scoped data**: All operations filtered by `matter_id`

### Gaps

#### 1. No chunk quality scoring
**Impact: HIGH.** Legal corpora contain significant noise: boilerplate headers/footers, table of contents entries, exhibit labels, privilege log entries, redaction markers, and OCR artifacts. These become chunks that pollute retrieval results.

No scoring exists to measure:
- **Coherence**: Is the chunk internally coherent or a random fragment?
- **Information density**: What fraction is substantive content vs. boilerplate?
- **Completeness**: Are sentences truncated? Are tables broken?

Without quality scores, retrieval treats a chunk of privilege log boilerplate the same as a chunk containing critical deposition testimony.

#### 2. No contextual metadata enrichment
GLiNER extracts entities, but chunks lack:
- **Topic classification**: What legal issue does this chunk discuss? (damages, liability, timeline, procedural, etc.)
- **Temporal context**: What time period does this chunk reference? (extracted dates, relative references resolved)
- **Document role**: Is this a key finding, supporting detail, procedural boilerplate, or legal analysis?
- **Privilege indicators at chunk level**: Currently only at document level

This metadata would enable faceted filtering at query time (e.g., "only search deposition chunks from 2008-2010 discussing damages").

#### 3. Near-duplicate detection is feature-flagged off by default
The MinHash + LSH dedup pipeline exists but is disabled. Legal corpora have massive duplication (email threads, document versions, boilerplate contracts). Without active dedup, retrieval returns redundant chunks that waste the LLM's context window.

#### 4. No document-level summarization
Each document lacks a generated summary. Document summaries would:
- Enable Anthropic-style contextual chunk prefixes (see Dimension 2)
- Support document-level search and browsing
- Feed into GraphRAG-style community summarization

### Recommendations (Priority Order)

1. **Chunk quality scoring** — Add a scoring step after chunking that evaluates each chunk for coherence, information density, and completeness. Store scores in Qdrant payload metadata. Use scores to:
   - Filter out low-quality chunks (score < threshold) at retrieval time
   - Weight retrieval results by quality (boost high-quality chunks)
   - Dashboard for monitoring ingestion quality over time
   - Implementation: heuristic scoring (sentence count, avg sentence length, boilerplate pattern matching) + optional LLM scoring for borderline cases
   - New file: `app/ingestion/quality_scorer.py`
   - Feature-flag: `ENABLE_CHUNK_QUALITY_SCORING`

2. **Enable near-duplicate detection by default** — The implementation exists. Flip `ENABLE_NEAR_DUPLICATE_DETECTION` to `true` and ensure dedup clusters are used at retrieval time to avoid returning redundant chunks.

3. **Document summarization at ingestion** — Generate a 2-3 sentence summary of each document using the existing LLM client. Store in PostgreSQL `documents.metadata_` and use as context for chunk prefixes.
   - New ingestion stage between PARSING and CHUNKING
   - Feature-flag: `ENABLE_DOCUMENT_SUMMARIES`

4. **Topic classification per chunk** — Use GLiNER or a lightweight classifier to tag chunks with legal topics. Store in Qdrant payload for faceted filtering. Medium effort.

---

## Dimension 5: Hybrid Retrieval & Reranking — 7/10

### What NEXUS does well
- **Native Qdrant RRF fusion**: Dense + sparse prefetch with `FusionQuery(Fusion.RRF)` — no Python-side fusion
- **Configurable prefetch multiplier**: Controls precision/recall tradeoff (default 2x)
- **Parallel text + graph retrieval**: `HybridRetriever` runs Qdrant and Neo4j concurrently
- **Graph-enhanced retrieval**: GLiNER extracts entities from query (threshold 0.5, higher than ingestion's 0.3), fetches entity neighborhoods from Neo4j
- **Visual reranking**: ColQwen2.5 MaxSim blend (weight 0.3) — feature-flagged
- **Matter-scoped privilege filtering**: At the Qdrant payload filter level

### Gaps

#### 1. Reranking is underutilized
**Impact: HIGH.** NEXUS has `BAAI/bge-reranker-v2-m3` implemented but **feature-flagged off**. Databricks research shows reranking improves retrieval quality by up to **48%**. The 2025/2026 production standard is:
1. Retrieve top-50 via hybrid search
2. Rerank to top-10 with cross-encoder

NEXUS retrieves top-20 without reranking by default. This means the LLM receives 20 chunks where only ~5-8 may be truly relevant, wasting context window and increasing hallucination risk.

#### 2. No retrieval quality validation (CRAG pattern)
Before generation, no node evaluates whether retrieved chunks are actually relevant to the query. The `check_relevance` node in V1 exists but is lightweight. A proper CRAG-style grader would:
- Score each chunk's relevance to the query (0-1)
- If average relevance < threshold, rewrite the query and retry
- If no relevant chunks after retry, respond with "insufficient evidence" rather than hallucinating

This is the **primary mechanism for preventing hallucinations from irrelevant context** — the #1 cause of RAG failures in production.

#### 3. No RRF weight tuning
Qdrant supports per-prefetch weights (e.g., 3.0 for dense, 1.0 for sparse). Currently, both prefetches have equal weight. For legal text, sparse/keyword matching may deserve higher weight for entity-name queries, while dense deserves higher weight for conceptual queries.

#### 4. No query-adaptive retrieval depth
All queries get the same top-20 retrieval depth. Simple factual queries ("What is the address of X?") need 3-5 chunks. Complex analytical queries ("What was the relationship between A and B over 2005-2010?") may need 30-50 chunks across multiple retrieval rounds.

### Recommendations

1. **Enable reranking by default** — Flip `ENABLE_RERANKER` to `true`. The BGE reranker v2 is already implemented and lazy-loaded. Increase initial retrieval to top-40, rerank to top-10. Estimated improvement: **30-48% retrieval quality**.

2. **Add CRAG-style retrieval grading** — New node in the LangGraph pipeline between `retrieve` and `synthesize`. Score each chunk's relevance. If median relevance < 0.5, trigger query rewrite and re-retrieval (max 1 retry). If still poor, respond with "insufficient evidence" with explanation.
   - Modify: `app/query/graph.py`, new `app/query/grader.py`
   - Template in: `app/query/prompts.py`

3. **Tune RRF weights** — Use the existing evaluation framework to sweep dense:sparse weight ratios. Legal queries often benefit from higher sparse weight (exact name matching).

4. **Adaptive retrieval depth** — Use the `classify` node output to set retrieval depth: factual=10, analytical=30, exploratory=40, timeline=30.

---

## Dimension 6: Query Orchestration — 9/10

### What NEXUS does well
- **Dual query graphs**: V1 (9-node sequential) + Agentic (ReAct with 12 tools) — covers simple and complex queries
- **`create_react_agent`** with `ToolNode`: Follows LangGraph 2025/2026 best practices exactly
- **12 specialized tools**: vector_search, graph_query, temporal_search, entity_lookup, document_retrieval, case_context, sentiment_search, hot_doc_search, context_gap_search, communication_matrix, topic_cluster, network_analysis
- **Security via `InjectedState`**: matter_id and privilege filters injected from graph state, never from LLM tool calls
- **Case context resolution**: Auto-injected claims/parties/timeline from anchor document
- **Tool budget enforcement**: Max 5 calls per query with saturation detection
- **Post-agent processing**: Citation verification + follow-up generation run after agent completes

### Gaps
- **No self-reflection loop**: If `verify_citations` finds unfaithful claims, the pipeline terminates rather than triggering re-retrieval. Adding a conditional edge from verification failure back to the agent would implement Self-RAG.
- **No adaptive routing**: The choice between V1 and Agentic graphs is manual (API parameter). An automatic router based on query complexity would improve UX.

### Recommendations
1. **Self-reflection loop** — Add conditional edge: if `verify_citations` finds faithfulness < 0.8, route back to `investigation_agent` with failed claims highlighted. Max 1 retry.
2. **Automatic graph routing** — Use the existing `classify` node to route simple factual queries to V1 (faster, cheaper) and complex queries to the agentic graph.

---

## Dimension 7: Citation & Faithfulness — 8/10

### What NEXUS does well
- **Cite-every-claim rule**: Enforced in both V1 and agentic system prompts
- **Post-agent citation verification**: Independent `verify_citations` node decomposes response into atomic claims and matches against sources
- **Citation extraction**: Regex-based extraction of `[Source: filename, Page N]` patterns
- **Three citation metrics**: citation_accuracy, hallucination_rate, post_rationalization_rate (Wallat et al. 2024)
- **Quality gates**: faithfulness >= 0.95, citation_accuracy >= 0.90, hallucination_rate < 0.05

### Gaps

#### 1. No per-citation confidence scores
The UI currently shows citations as binary (present/absent). Lawyers need to know **how confident** the system is in each citation. A citation backed by a verbatim quote deserves higher confidence than one inferred from context.

#### 2. No HalluGraph-style structural verification
HalluGraph (arXiv 2512.01659) extracts entity graphs from both retrieved context and generated response, then computes structural alignment. This catches a class of hallucinations that text-matching misses: when the LLM fabricates relationships between real entities.

### Recommendations
1. **Citation confidence scores** — Extend `verify_citations` to output 0.0-1.0 confidence per citation. Display in the frontend with visual indicators (green/yellow/red). Low effort, high value for legal defensibility.
2. **Entity-graph alignment check** — Extract entities and relationships from the generated response. Verify each relationship exists in the retrieved context or Neo4j graph. Flag fabricated relationships. Medium effort.

---

## Dimension 8: Evaluation & Observability — 6/10

### What NEXUS does well
- **Evaluation framework exists**: `app/evaluation/` with ground-truth Q&A datasets, retrieval metrics (MRR/Recall/NDCG@10), RAGAS integration, citation metrics
- **Three dataset types**: GroundTruthItem, AdversarialItem, LegalBenchItem
- **Tuning framework**: Predefined sweep experiments (reranker impact, prefetch multiplier, entity threshold)
- **Quality gates defined**: faithfulness >= 0.95, citation_accuracy >= 0.90
- **LangSmith integration**: Production tracing available
- **AI audit logging**: Every LLM call logged with prompt hash, tokens, latency

### Gaps

#### 1. Evaluation is not operationalized
The evaluation framework exists in code but is not running in CI/CD. There are no automated quality gates that block deployments. The tuning framework has a placeholder for full-mode execution ("not yet implemented").

#### 2. No per-query-type metrics
Legal queries vary enormously: timeline reconstruction, entity relationship mapping, factual lookup, privilege determination. Aggregate metrics (average MRR) hide systematic failures on specific query types. A system with 85% average accuracy may fail 100% on timeline queries.

#### 3. No retrieval quality monitoring in production
LangSmith traces exist but there's no automated alerting on retrieval quality degradation. No dashboard tracking MRR/recall trends over time. No anomaly detection for queries that return unusually low-relevance chunks.

#### 4. No adversarial testing in CI
The `AdversarialItem` schema exists (false_premise, privilege_trick, ambiguous_entity) but there's no evidence of a populated adversarial test suite running in CI.

### Recommendations

1. **Operationalize evaluation in CI/CD** — Run the evaluation suite on every PR that touches ingestion, retrieval, or generation code. Block merges that degrade quality below gates. Use existing GitHub Actions infrastructure.
   - Modify: `.github/workflows/` to add evaluation step
   - Prerequisite: Populate ground-truth dataset with representative queries

2. **Per-query-type dashboards** — Segment all metrics by query archetype (factual, analytical, timeline, entity-relationship). Track trends. Alert on per-type degradation.

3. **Populate adversarial test suite** — Create 20-30 adversarial test cases covering:
   - False premise queries ("When did X acquire Y?" when no acquisition occurred)
   - Privilege boundary probes ("Show me all privileged communications")
   - Entity confusion ("Tell me about John Smith" when multiple John Smiths exist)
   - Temporal confusion ("What happened before the merger?" with ambiguous merger reference)

4. **Production quality monitoring** — Add LangSmith evaluator that scores every production query for retrieval relevance and generation faithfulness. Alert when rolling average drops below threshold.

---

## Summary: Top Recommendations by Priority

### Must-Do (Highest Impact, Justified Effort)

| # | Recommendation | Dimension | Est. Impact | Key Files |
|---|---------------|-----------|-------------|-----------|
| 1 | **Contextual chunk enrichment** (Anthropic-style context prefixes at ingestion) | Chunking + Data Quality | 49-67% fewer retrieval failures | New `app/ingestion/contextualizer.py`, modify `tasks.py` |
| 2 | **Enable reranking** (flip feature flag, increase retrieval depth to 40→10) | Retrieval | 30-48% retrieval quality improvement | `app/query/retriever.py`, config |
| 3 | **CRAG-style retrieval grading** (score chunk relevance, rewrite if poor) | Retrieval | Primary hallucination prevention | New `app/query/grader.py`, modify `graph.py` |
| 4 | **Chunk quality scoring** (coherence, density, completeness at ingestion) | Data Quality | Filters noise from retrieval | New `app/ingestion/quality_scorer.py` |

### Should-Do (High Impact, Moderate Effort)

| # | Recommendation | Dimension | Est. Impact | Key Files |
|---|---------------|-----------|-------------|-----------|
| 5 | **Enable near-duplicate detection** (flip existing feature flag) | Data Quality | Eliminates redundant chunks | Config change only |
| 6 | **Citation confidence scores** (0-1 per citation, shown in UI) | Citation | Legal defensibility | `app/query/nodes.py`, frontend |
| 7 | **Operationalize evaluation in CI/CD** (quality gates block deploys) | Evaluation | Prevents regressions | `.github/workflows/`, `evaluation/` |
| 8 | **Adversarial test suite** (20-30 cases: false premise, privilege probes) | Evaluation | Catches edge-case failures | `evaluation/` datasets |

### Could-Do (Strategic, Higher Effort)

| # | Recommendation | Dimension | Est. Impact | Key Files |
|---|---------------|-----------|-------------|-----------|
| 9 | **Self-reflection loop** (re-retrieve on citation verification failure) | Orchestration | Reduces unfaithful responses | `app/query/graph.py` |
| 10 | **SPLADE for sparse retrieval** (learned query expansion, vocabulary mismatch) | Embedding | Better legal term matching | `app/ingestion/sparse_embedder.py` |
| 11 | **GraphRAG community summaries** (global sensemaking) | Orchestration | Enables corpus-wide queries | `app/entities/graph_service.py` |
| 12 | **Document summarization at ingestion** (feeds contextual prefixes) | Data Quality | Foundation for #1 | New ingestion stage |

---

## Verification Plan

To validate these improvements after implementation:

1. **Before any changes**: Run full evaluation suite to establish baseline metrics (MRR, Recall, NDCG, faithfulness, citation accuracy)
2. **After each change**: Re-run evaluation suite. Compare against baseline. Require improvement or no regression.
3. **Contextual retrieval**: A/B test with 50 representative queries. Compare retrieval recall with/without context prefixes.
4. **Reranking**: Sweep reranker top-n (5, 10, 15, 20) on evaluation dataset. Measure MRR@10 and NDCG@10.
5. **CRAG grader**: Test with 20 adversarial queries designed to trigger poor retrieval. Measure hallucination rate reduction.
6. **End-to-end**: Run full adversarial + ground-truth test suite. All quality gates must pass.
