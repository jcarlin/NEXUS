# Research: Cognee + GraphRAG Evaluation for NEXUS

*Date: 2025-03-15*
*Status: Research complete, implementation planned*
*References: [cognee](https://github.com/topoteretes/cognee) (v0.5.5, Apache 2.0), [Microsoft GraphRAG](https://github.com/microsoft/graphrag)*

## Context

Evaluation of [cognee](https://github.com/topoteretes/cognee) — an open-source knowledge engine that builds knowledge graphs from documents for AI agent memory — and Microsoft's [GraphRAG](https://github.com/microsoft/graphrag) for potential adoption into NEXUS. Research conducted by cloning the cognee repo, reading source code, fetching documentation, and mapping component-by-component to NEXUS's existing architecture.

**Questions answered:**
1. How much of NEXUS could we swap out for cognee?
2. How feasible is adoption on a side branch for A/B testing?
3. Does cognee need extension for local inference?
4. Why aren't we using GraphRAG, and what does it cover?

---

## 1. What Is Cognee?

**Core concept**: ECL pipeline (Extract, Cognify, Load) — `add()` → `cognify()` → `search()`

**Architecture** (from source code review):
- **Ingestion**: `add()` ingests files/text/URLs into datasets, stores in relational DB (SQLite default, Postgres optional)
- **Cognify**: LLM extracts entities + relationships from each chunk → builds knowledge graph → stores in graph DB + vector DB
- **Search**: 12+ search types including `GRAPH_COMPLETION`, `RAG_COMPLETION`, `TEMPORAL`, `CYPHER`, `TRIPLET_COMPLETION`, `GRAPH_COMPLETION_COT` (chain-of-thought)
- **Memify**: Post-cognify enrichment with additional rules and context

**Key technical details** (from `cognee/tasks/graph/extract_graph_from_data.py`):
- Entity extraction via `LLMGateway.acreate_structured_output()` using Instructor — extracts `KnowledgeGraph` Pydantic model with nodes + edges
- Ontology grounding via `BaseOntologyResolver` — validates extracted entities against OWL ontologies (rdflib)
- Provenance stamping on all DataPoints (pipeline name, task name)
- Graph integration: expand nodes/edges, retrieve existing edges, upsert with deduplication

**Storage backends**:
- **Graph**: Kuzu (default), Neo4j, FalkorDB, Neptune, Memgraph
- **Vector**: LanceDB (default), PGVector, ChromaDB. Qdrant listed in docs but NOT in core code (community repo only)
- **Relational**: SQLite (default), PostgreSQL

**v0.5.5, beta status, Apache 2.0 license, Python 3.10-3.13**

---

## 2. What Is GraphRAG?

Microsoft's approach to RAG that builds **hierarchical knowledge graphs with community detection** instead of flat vector search.

**How it works**:
1. LLM extracts entities + relationships from each text chunk
2. Builds a knowledge graph
3. Runs **Hierarchical Leiden Algorithm** for community detection at multiple levels
4. LLM generates **community reports** (summaries) for each community at each level
5. Two query modes:
   - **Local Search**: Entity-centric, graph traversal from specific entities (~80-100ms)
   - **Global Search**: Map-reduce across all community reports for corpus-wide patterns (~500ms-2s, ~610K tokens/query)

**Why it matters for legal**:
- Multi-hop reasoning: case → ruling → principle → related case
- Party network mapping across 50K+ pages
- Timeline reconstruction through entity chains
- Corpus-wide pattern discovery (e.g., "what regulatory themes span all contracts?")

**Cost**: Very LLM-intensive. A 32K-word book costs ~$7 to index. At 50K pages, indexing cost is $3,500-17,500 (at GPT-4 rates). Dynamic community selection reduces query cost by 77%.

**Local model support**: Via OpenAI-compatible endpoints (Ollama, vLLM). Quality degrades with models <70B for extraction tasks.

---

## 3. NEXUS vs Cognee: Component-by-Component Comparison

### What Cognee Has That NEXUS Doesn't

| Feature | Cognee | NEXUS Status | Value for NEXUS |
|---------|--------|-------------|-----------------|
| **Ontology grounding** | OWL ontologies, rdflib, fuzzy matching | None | HIGH — could improve entity normalization for legal concepts (e.g., "breach of contract" = "contractual breach") |
| **12 search types** | GRAPH_COMPLETION, COT, TEMPORAL, CYPHER, TRIPLET, etc. | 1 hybrid query pipeline | MEDIUM — temporal search and chain-of-thought over graph are interesting |
| **Feedback weights** | Node/edge feedback weights for learning | None | MEDIUM — could improve retrieval quality over time |
| **Memify** | Post-cognify graph enrichment with rules | None | LOW — NEXUS has chunk enrichment already |
| **Graph visualization UI** | Built-in at `/visualize` | Frontend has basic graph view | LOW — already have this |

### What NEXUS Has That Cognee Doesn't

| Feature | NEXUS | Cognee Status | Risk of Swapping |
|---------|-------|--------------|------------------|
| **Qdrant with native RRF** | Dense + sparse + summary vectors, native fusion via `prefetch` + `FusionQuery` | NO Qdrant adapter in core code (only LanceDB, PGVector, ChromaDB). Qdrant is "community repo" only | CRITICAL — would lose our best retrieval feature |
| **GLiNER NER** | ~50ms/chunk CPU inference, no LLM needed | LLM-only extraction (~$0.01-0.05/chunk) | CRITICAL — 50K pages × LLM extraction = massive cost |
| **LangGraph agentic orchestration** | 6 agents, 17 tools, `create_react_agent` | Simple pipeline, no agent framework | HIGH — would lose investigation agent, case setup agent, etc. |
| **Citation verification** | Post-agent `verify_citations` node checks each claim | None | HIGH — legal requirement |
| **Self-reflection** | Conditional retry when faithfulness < threshold | None | HIGH |
| **HyDE** | Hypothetical document embeddings for dense retrieval | None | MEDIUM |
| **Multi-representation indexing** | Triple RRF (dense + sparse + summary vectors) | Single vector only | HIGH |
| **Privilege enforcement at data layer** | Qdrant filter + SQL WHERE + Neo4j Cypher | Dataset-level permissions only | HIGH — legal compliance |
| **Production audit trail** | Every API + LLM call logged with tokens, latency, prompt hash | Basic logging | HIGH |
| **SSE streaming** | Sources before generation, token-by-token streaming | No streaming | MEDIUM |
| **Semantic chunking (Docling)** | Structure-aware chunking from document layout | LLM-based paragraph chunking (Docling optional extra but not the default) | HIGH — critical for legal docs with tables, headers |
| **BGE-M3 embeddings** | Dense + sparse in single forward pass | FastEmbed default | MEDIUM |

### Shared Ground (Both Have)

| Feature | NEXUS Implementation | Cognee Implementation |
|---------|---------------------|----------------------|
| **Neo4j** | Native driver, parameterized Cypher | Neo4j adapter via `GraphDBInterface` |
| **Instructor** | Structured LLM output | Structured LLM output via `LLMGateway` |
| **Multi-tenant** | Matter-scoped everything | Dataset-scoped with permissions |
| **Docling** | Default document parser | Optional extra (`pip install cognee[docling]`) |
| **structlog** | Structured logging | Structured logging |
| **tenacity** | Retry with backoff | Retry with backoff |
| **Alembic** | Schema migrations | Schema migrations |
| **FastAPI** | API layer | API layer |
| **Ollama/vLLM** | Full local inference support | Full local inference support |

---

## 4. Does Cognee Need Extension for Local Inference?

**No — cognee already supports local inference out of the box:**

```bash
# Ollama (from cognee/.env.template)
LLM_PROVIDER="ollama"
LLM_MODEL="llama3.1:8b"
LLM_ENDPOINT="http://localhost:11434/v1"
EMBEDDING_PROVIDER="ollama"
EMBEDDING_MODEL="nomic-embed-text:latest"

# vLLM
LLM_PROVIDER="custom"
LLM_MODEL="hosted_vllm/your-model"
LLM_ENDPOINT="http://localhost:8000/v1"

# llama.cpp
pip install cognee[llama-cpp]
```

Cognee uses `litellm` under the hood which routes to any OpenAI-compatible endpoint. Same pattern as NEXUS's `app/common/llm.py`.

---

## 5. Why NEXUS Doesn't Use GraphRAG (and Whether It Should)

### Why we haven't adopted it:
1. **Cost**: GraphRAG's indexing is extremely LLM-intensive. At 50K+ pages, indexing cost alone would be $3,500-17,500 (at GPT-4 rates)
2. **NEXUS already has graph-based retrieval**: Neo4j multi-hop traversal in `app/query/retriever.py` + entity graph in `app/entities/`
3. **GLiNER is faster and cheaper**: NER at ~50ms/chunk vs LLM extraction at ~2-5s/chunk
4. **Hybrid retrieval is already strong**: Dense + sparse + summary vectors with native RRF fusion
5. **Community detection overhead**: Leiden algorithm + community report generation adds complexity without clear legal-domain ROI

### What GraphRAG would add:
1. **Hierarchical community detection** — group related entities across documents automatically (e.g., all parties in a regulatory dispute cluster together)
2. **Global search** — answer "what are all the themes across this 50K page corpus?" (NEXUS can't do this well today)
3. **Community reports** — pre-computed summaries at multiple granularity levels

### Recommendation:
**Don't adopt GraphRAG wholesale. Cherry-pick community detection.** Specifically:
- Add Leiden community detection as a post-processing step on NEXUS's existing Neo4j graph
- Generate community summaries for the top 2-3 levels
- Add a "global search" query mode that queries community summaries
- Keep everything else (GLiNER, Qdrant, LangGraph agents, citation verification)

---

## 6. How Much Code Could We Swap Out?

### Realistically swappable (LOW risk):
- **Graph construction pipeline** — Replace `app/entities/service.py` graph-building logic with cognee's `extract_graph_from_data` + ontology resolver. ~500 lines. But we'd lose GLiNER speed advantage.
- **Search types** — Add cognee-inspired search modes (temporal, chain-of-thought over graph) as new query tools in `app/query/tools.py`. ~200-400 lines new code.

### NOT swappable (would break critical features):
- **Retrieval pipeline** (`app/query/retriever.py`) — Cognee has no Qdrant support, no RRF fusion, no sparse vectors. Swapping this would be a massive regression.
- **Agentic orchestration** (`app/query/graph.py`) — Cognee has no agent framework. Would lose 6 agents + 17 tools.
- **Ingestion pipeline** (`app/ingestion/`) — Cognee's chunking is LLM-based paragraphs. NEXUS uses Docling structure-aware chunking. Swapping would degrade quality on legal docs.
- **Entity extraction** — Cognee uses LLM for NER. At 50K pages, this costs 100-1000x more than GLiNER.
- **Citation verification, self-reflection, HyDE** — None of this exists in cognee.

### Bottom line:
**~10-15% of NEXUS code could benefit from cognee patterns. ~85-90% should stay as-is or would regress.**

---

## 7. Integration Plan: Side Branch A/B Testing

### Approach: Selective Integration, Not Replacement

Feature-flag new capabilities inspired by cognee/GraphRAG without replacing working NEXUS components. All three phases to be developed in parallel on a side branch.

### Phase 1: Community Detection (GraphRAG-inspired)
**New feature flag: `ENABLE_GRAPH_COMMUNITIES`**

1. Add Leiden community detection on NEXUS's existing Neo4j entity graph
2. Generate community summaries at 2-3 hierarchy levels via LLM
3. Add `global_search` tool to the investigation agent
4. Store community summaries as new Qdrant collection for vector search

**Files to create/modify:**
- `app/analytics/communities.py` — NEW: Leiden algorithm on Neo4j graph (use `graspologic` or `networkx` community detection)
- `app/analytics/community_summarizer.py` — NEW: LLM-generated community reports
- `app/query/tools.py` — ADD: `global_search` tool that queries community summaries
- `app/ingestion/tasks.py` — ADD: post-ingestion community detection step (optional, feature-flagged)
- `app/config.py` — ADD: `enable_graph_communities: bool = False`
- `app/feature_flags/registry.py` — ADD: `FlagMeta` entry

### Phase 2: Ontology-Grounded Entity Normalization (Cognee-inspired)
**New feature flag: `ENABLE_ONTOLOGY_GROUNDING`**

1. Add OWL ontology support for legal entity types (person, organization, court, statute, etc.)
2. Validate extracted entities against ontology during ingestion
3. Improve entity deduplication with ontology-aware matching

**Files to create/modify:**
- `app/entities/ontology.py` — NEW: ontology resolver (rdflib-based, similar to cognee's)
- `app/entities/service.py` — MODIFY: add ontology validation step after GLiNER extraction
- `app/config.py` — ADD: `enable_ontology_grounding: bool = False`

### Phase 3: Temporal Graph Search (Cognee-inspired)
**New feature flag: `ENABLE_TEMPORAL_SEARCH`**

1. Add temporal edges to Neo4j graph (date → event → entity relationships)
2. Add `temporal_search` tool to investigation agent
3. Enable timeline reconstruction queries

**Files to create/modify:**
- `app/entities/temporal.py` — NEW: temporal entity extraction and graph construction
- `app/query/tools.py` — ADD: `temporal_search` tool
- `app/config.py` — ADD: `enable_temporal_search: bool = False`

### Phase 4: A/B Testing Framework
1. Add query routing: randomly assign queries to "standard" vs "enhanced" (community + ontology) pipelines
2. Compare retrieval metrics (MRR, Recall, NDCG) and faithfulness scores
3. Use existing evaluation framework (`app/evaluation/`, `scripts/evaluate.py`)

**Files to modify:**
- `app/query/graph.py` — ADD: A/B routing logic (feature-flagged)
- `app/evaluation/` — ADD: A/B comparison metrics

---

## 8. Dependency Impact

### New dependencies needed:
- `graspologic>=3.4.0` — Hierarchical Leiden algorithm (MIT license)
- `rdflib>=7.0.0` — OWL ontology parsing (BSD license) — already in cognee's deps
- No new infra required (uses existing Neo4j, Qdrant, LLM)

### NOT needed:
- `cognee` as a pip dependency — we cherry-pick patterns, not the library itself
- `graphrag` (Microsoft) — too heavyweight and opinionated; we implement community detection directly
- No new databases or services

---

## 9. Local Inference Considerations

Both cognee and GraphRAG support local models, and **NEXUS already has full local inference support**:
- `LLM_PROVIDER=ollama/vllm` in `app/config.py`
- `EmbeddingProvider` with 6 implementations in `app/common/embedder.py`
- BGE-M3 produces dense+sparse locally

The new community detection features would use the existing LLM abstraction (`app/common/llm.py`) — no additional local inference support needed.

**Note**: Community summary generation quality degrades with models <70B. Recommend using the best available model for this step (can be a different model tier via `app/llm_config/`).

---

## 10. Verification Plan

### Testing community detection:
```bash
# Unit tests for community detection
pytest tests/test_analytics/test_communities.py -v

# Integration test with existing Neo4j graph
pytest tests/test_analytics/test_community_integration.py -v

# A/B evaluation
python scripts/evaluate.py --mode ab --features communities,ontology
```

### Testing ontology grounding:
```bash
pytest tests/test_entities/test_ontology.py -v
```

### Full regression:
Run parallel test suite (4 agents per CLAUDE.md rule 43) to ensure no regressions.

---

## 11. Summary

| Question | Answer |
|----------|--------|
| **How much code could we swap?** | ~10-15% (graph construction patterns, search types). 85-90% should stay. |
| **Feasible for A/B testing?** | Yes — feature-flag new capabilities, don't replace existing ones |
| **Need to extend cognee for local inference?** | No — already supports Ollama, vLLM, llama.cpp |
| **Why not using GraphRAG?** | Cost ($3.5-17.5K to index 50K pages), complexity, and NEXUS already has strong hybrid retrieval. But community detection is worth cherry-picking. |
| **What's most valuable from cognee?** | Ontology grounding, temporal search, feedback weights |
| **What's most valuable from GraphRAG?** | Hierarchical community detection + global search |
| **What should we NOT adopt?** | LLM-based NER (have GLiNER), cognee's vector layer (no Qdrant/RRF), cognee's simple pipeline (have LangGraph agents) |
