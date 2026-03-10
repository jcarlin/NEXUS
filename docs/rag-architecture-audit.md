# RAG Architecture Audit

**Date**: 2025-03-10
**Scope**: Full codebase audit against comprehensive RAG system reference architecture

## Overview

Audit of the NEXUS codebase against a reference RAG architecture covering: RAG Types, Query Construction, Routing, Retrieval, Reranking, Refinement, Generation, Indexing, and Evaluation.

**Result**: ~75% of the reference architecture is implemented. Gaps cluster around **query intelligence** — the system retrieves well once it has the right query, but doesn't yet optimally transform user intent across all data sources.

---

## Current Coverage

### RAG Types

| Component | Status | Implementation |
|-----------|--------|---------------|
| RAC/RRF Fusion | **Full** | Native Qdrant RRF via `prefetch` + `FusionQuery` (`app/common/vector_store.py:224-236`) |
| Query Rewrite | **Partial** | Single rewrite in `rewrite_query` node + reformulation on low relevance (`app/query/nodes.py:121-143`) |
| Decomposition | **Implicit** | Agentic tool loop via `create_react_agent` decides tool strategy; CoVe decomposes *responses* into claims for verification |
| Multi-Query | **Missing** | No parallel query variant generation |
| HyDE | **Missing** | No hypothetical document embedding |

### Query Construction

| Component | Status | Implementation |
|-----------|--------|---------------|
| Vector DB | **Full** | Qdrant dense (1024d) + sparse (BM42) hybrid search (`app/query/retriever.py:58-89`) |
| Graph DB | **Full** | Hand-crafted parameterized Cypher queries (`app/entities/graph_service.py:56-1247`) |
| Relational DB | **Full** | Hand-crafted parameterized SQL via `sqlalchemy.text()` across all service modules |
| Text-to-Cypher | **Missing** | No natural language → Cypher generation |
| Text-to-SQL | **Missing** | No natural language → SQL generation |

### Routing

| Component | Status | Implementation |
|-----------|--------|---------------|
| Logical Route | **Full** | LLM classifies query type in `classify_query` node; agent selects from 12 tools (`app/query/nodes.py:98-117`) |
| Semantic Route | **Partial** | Tier classification (fast/standard/deep) controls recursion limits + skips verification (`app/query/nodes.py:575-632`). No per-query-type prompt selection. |

### Retrieval

| Component | Status | Implementation |
|-----------|--------|---------------|
| Dense vectors | **Full** | Qdrant 1024d COSINE, multi-provider embeddings (`app/common/embedder.py`) |
| Sparse vectors | **Full** (flag off) | BM42 via FastEmbed (`app/ingestion/sparse_embedder.py`, `ENABLE_SPARSE_EMBEDDINGS`) |
| Graph traversal | **Full** | Neo4j multi-hop via `HybridRetriever.retrieve_graph()` (`app/query/retriever.py`) |
| Multi-source fusion | **Full** | Parallel text + graph retrieval via `asyncio.gather()` (`app/query/retriever.py:153-186`) |
| Reranking (cross-encoder) | **Full** (flag off) | BGE-Reranker-v2-M3 local or TEI remote (`app/query/reranker.py`, `ENABLE_RERANKING`) |
| Reranking (visual) | **Full** (flag off) | ColQwen2.5 MaxSim blend (`app/ingestion/visual_embedder.py`, `ENABLE_VISUAL_EMBEDDINGS`) |
| Relevance threshold | **Full** | `avg_score >= 0.3` routes to reformulation (`app/query/nodes.py:264-278`) |
| Context dedup | **Full** | Hash-based dedup on graph results |

### Generation

| Component | Status | Implementation |
|-----------|--------|---------------|
| Active retrieval (agentic) | **Full** | `create_react_agent` with 12 tools iteratively retrieves before synthesizing (`app/query/graph.py`) |
| Citation grounding | **Full** | Chain-of-Verification: decompose → retrieve → judge per claim (`app/query/nodes.py`) |
| SSE streaming | **Full** | Sources sent before generation, token-by-token LLM streaming (`app/query/router.py`) |
| Self-RAG | **Implicit** | CoVe + agentic tool loop covers the core value; no standalone Self-RAG loop |

### Indexing

| Component | Status | Implementation |
|-----------|--------|---------------|
| Semantic split | **Full** | Paragraph-boundary + table-aware chunking, 512 tok / 64 overlap (`app/ingestion/chunker.py`) |
| Special embeddings | **Full** | BM42 sparse (`sparse_embedder.py`) + ColQwen2.5 visual multi-vector (`visual_embedder.py`) |
| Topic clustering | **Full** (flag off) | BERTopic with all-MiniLM-L6-v2 (`app/analytics/clustering.py`, `ENABLE_TOPIC_CLUSTERING`) |
| Multi-Representation | **Missing** | No chunk summaries stored alongside full text for summary-level retrieval |
| RAPTOR (Hierarchical) | **Missing** | No recursive abstractive processing or cluster-based hierarchical summaries |

### Evaluation

| Component | Status | Implementation |
|-----------|--------|---------------|
| RAGAS | **Full** | Faithfulness, answer_relevancy, context_precision (`app/evaluation/metrics/generation.py`) |
| Custom metrics | **Full** | MRR, Recall, NDCG, Precision, citation accuracy, hallucination rate, post-rationalization rate |
| Quality gates | **Full** | Faithfulness ≥ 0.95, citation accuracy ≥ 0.90, hallucination < 0.05 |
| Grouse / DeepEval | **Missing** | Not integrated |

---

## Priority Roadmap — Missing Components

Prioritized for legal RAG where lawyers:
- Know what they're looking for (the legal issue, relationship, or timeline)
- May not phrase questions optimally for retrieval (vocabulary mismatch)
- Don't know which exact documents contain the answer

### Tier 1 — High Impact (add first)

#### 1. Multi-Query Expansion

**Why**: Lawyers may not phrase questions in the same vocabulary as the documents. Generating 3-5 reformulations (synonyms, legal terminology variants, broader/narrower framings) dramatically improves recall on the first try.

**Example**: "What did Smith know about the deal?" should also search "awareness of the transaction", "knowledge of the agreement", "involvement in the merger".

**Where**: New node in `app/query/nodes.py` between `rewrite_query` and `retrieve`. Generate variants via LLM, run parallel Qdrant searches, fuse results.

#### 2. Semantic Prompt Routing

**Why**: Currently one `INVESTIGATION_SYSTEM_PROMPT` for everything. Timeline questions, privilege reviews, and deposition summaries all get the same instructions. Routing to specialized prompts yields higher-quality output per query type.

**Where**: Extend `classify_query` in `app/query/nodes.py` to select from prompt templates in `app/query/prompts.py`. Add templates: timeline-builder, privilege-analyzer, deposition-summarizer, communication-mapper.

#### 3. Explicit Question Decomposition

**Why**: Complex questions like "Compare Smith's testimony in the 2019 deposition with his email communications during the same period" implicitly require multi-hop retrieval. Explicit sub-question planning is more reliable and auditable than hoping the agent decomposes correctly via tool calls.

**Where**: New node in `app/query/nodes.py` that decomposes complex questions into sub-questions, retrieves for each, then synthesizes. Gate on query complexity classification.

#### 4. Text-to-Cypher Generation

**Why**: Relationship questions are central to legal work: "Who communicated with X between Y and Z?" The rich Neo4j schema is currently only accessible through predefined tools. Text-to-Cypher unlocks the full knowledge graph for natural language queries.

**Where**: New tool in `app/query/tools.py`. Use Instructor + schema context to generate parameterized Cypher. Validate before execution. Always scope by `matter_id`.

### Tier 2 — Medium Impact (add second)

#### 5. HyDE (Hypothetical Document Embeddings)

**Why**: Bridges vocabulary gap between how a lawyer asks and how a witness testified or contract was drafted. Generates a hypothetical answer and embeds *that* for retrieval — especially effective when question phrasing diverges from document language.

**Where**: Optional retrieval strategy in `app/query/retriever.py`. Generate hypothetical answer via LLM, embed it, use as query vector. Feature-flag gated.

#### 6. Multi-Representation Indexing

**Why**: Store chunk summaries alongside full text. Retrieve on summaries (broader semantic match), return full text (precise citations). Valuable for dense legal prose where chunk-level embeddings can miss the forest for the trees.

**Where**: New stage in ingestion pipeline (`app/ingestion/tasks.py`) that generates chunk summaries. Store as separate named vector or payload field in Qdrant. Modify retriever to optionally search on summaries.

#### 7. Text-to-SQL Generation

**Why**: Structured metadata queries: "How many documents mention Company X filed after January 2020?" Opens up the full relational schema to ad-hoc questions beyond what predefined tools offer.

**Where**: New tool in `app/query/tools.py`. Use Instructor + table schema context. Validate generated SQL. Always include `matter_id` filter. Read-only queries only.

### Tier 3 — Lower Priority

#### 8. RAPTOR (Hierarchical Indexing)

Recursive summarization into cluster hierarchies. More useful for broad exploratory questions across huge corpora. Lawyers typically drill into specific docs/date ranges. Low ROI given the ingestion cost.

#### 9. Grouse / DeepEval

Additional eval frameworks. Existing RAGAS + custom metrics with quality gates are already comprehensive. Nice for benchmarking but won't change user experience.

#### 10. Self-RAG (Standalone)

CoVe citation verification + agentic tool loop already covers the core value proposition. A full Self-RAG loop that decides *during* generation whether to retrieve more is architecturally expensive and the agentic tool loop already fills this role.
