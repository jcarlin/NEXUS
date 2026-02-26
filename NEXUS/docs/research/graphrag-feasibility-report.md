# GraphRAG Feasibility Report for NEXUS

**Date:** 2026-02-26
**Subject:** Evaluation of Microsoft GraphRAG and related approaches for the NEXUS Multimodal RAG Investigation Platform

---

## Executive Summary

NEXUS already implements a sophisticated hybrid RAG architecture with Neo4j knowledge graph, Qdrant vector search, and multi-modal retrieval. Microsoft's GraphRAG introduces **community detection and hierarchical summarization** — capabilities NEXUS currently lacks — that would specifically strengthen NEXUS's ability to answer **global/corpus-wide queries** (e.g., "What are the major themes across all 50,000 documents?"). However, full GraphRAG indexing at NEXUS's scale (50K+ legal documents) would be **prohibitively expensive** ($10K–$50K+ in LLM calls). **LazyGraphRAG** or a selective hybrid approach is the recommended path forward.

**Recommendation:** Adopt LazyGraphRAG concepts selectively — specifically community detection on NEXUS's existing Neo4j graph and query-time summarization — rather than replacing the current pipeline with Microsoft's full GraphRAG.

---

## 1. What Is Microsoft GraphRAG?

Microsoft GraphRAG is an LLM-powered pipeline that:

1. **Extracts entities and relationships** from text chunks using LLM calls
2. **Builds a knowledge graph** from those extractions
3. **Detects communities** using the Leiden algorithm (clusters of densely connected entities)
4. **Generates hierarchical summaries** of each community at multiple granularity levels
5. **Answers queries** by routing to either:
   - **Local Search:** Vector similarity + graph neighborhood (like traditional RAG + graph)
   - **Global Search:** Aggregates across all community summaries (unique to GraphRAG)

The key innovation is the **community hierarchy and pre-computed summaries**, which enable answering questions about the *entire corpus* without retrieving every document.

---

## 2. What NEXUS Already Has (Overlap Analysis)

| Capability | NEXUS Current | GraphRAG | Overlap? |
|---|---|---|---|
| Entity extraction | GLiNER (CPU, fast) + Instructor/LLM (optional) | LLM-only (expensive) | **Yes** — NEXUS is more cost-efficient |
| Relationship extraction | Instructor + Claude (tier 2, optional) | LLM-extracted per chunk | **Yes** — similar approach |
| Knowledge graph storage | Neo4j 5.x + Graphiti | Typically Parquet files or Neo4j | **Yes** — NEXUS is more mature |
| Vector search | Qdrant (dense + sparse, RRF fusion) | Vector store integration | **Yes** — NEXUS is more sophisticated |
| Multi-hop graph traversal | Neo4j Cypher queries in query pipeline | Graph neighborhood traversal | **Yes** |
| Entity resolution | Fuzzy matching + embeddings + co-occurrence | Basic deduplication | **Yes** — NEXUS is more robust |
| Multi-modal retrieval | ColQwen2.5 visual + text + graph | Text only | **NEXUS is ahead** |
| Community detection | **Not implemented** | Leiden algorithm | **Gap** |
| Hierarchical summaries | **Not implemented** | Pre-computed at index time | **Gap** |
| Global/corpus-wide queries | Limited (retrieval-bounded) | Strong (community summaries) | **Gap** |
| Streaming responses | SSE with progressive sources | Not a focus | **NEXUS is ahead** |
| Conversation memory | LangGraph PostgresCheckpointer | Not included | **NEXUS is ahead** |

### Key Gaps GraphRAG Would Fill

1. **Community Detection:** Identifying clusters of related entities (e.g., "all people connected to Company X through financial transactions") without explicit queries
2. **Hierarchical Summarization:** Pre-computed summaries at different granularity levels enabling corpus-wide questions
3. **Global Query Answering:** "What are the main patterns of financial misconduct across the entire document corpus?" — currently NEXUS can only answer this through retrieval-bounded results

---

## 3. Cost Analysis

### Full GraphRAG Indexing

Based on reported costs from production deployments:

| Scale | Estimated Cost (GPT-4o) | Estimated Cost (GPT-4o-mini) | Time |
|---|---|---|---|
| 100 documents | $50–$200 | $5–$20 | Hours |
| 1,000 documents | $500–$2,000 | $50–$200 | Days |
| 10,000 documents | $5,000–$20,000 | $500–$2,000 | Days–Weeks |
| 50,000 documents (NEXUS target) | $25,000–$100,000 | $2,500–$10,000 | Weeks |

**Verdict:** Full GraphRAG indexing at NEXUS scale is **cost-prohibitive**, especially since NEXUS already extracts entities and relationships more efficiently via GLiNER + selective LLM calls.

### LazyGraphRAG Alternative

| Metric | Full GraphRAG | LazyGraphRAG |
|---|---|---|
| Indexing cost | Very high (LLM per chunk) | **0.1% of GraphRAG** (same as vector RAG) |
| Query cost (global) | High (all communities) | **700x cheaper** for comparable quality |
| Query cost (local) | Moderate | Comparable |
| Quality (global queries) | Baseline | Comparable or better |

**LazyGraphRAG defers LLM summarization to query time**, using best-first + breadth-first iterative search. A single parameter controls the cost-quality tradeoff.

---

## 4. Performance Benchmarks

### Where GraphRAG Excels

- **Multi-hop reasoning:** 86.31% accuracy vs. 32–76% for other RAG approaches (RobustQA)
- **Complex entity queries:** Stable performance with 10+ entities per query (traditional RAG drops to 0%)
- **Comprehensiveness:** 70–80% win rate over naive RAG on global questions
- **Production case study:** Accuracy on complex multi-hop questions jumped from 43% to 91% after GraphRAG adoption in financial services

### Where GraphRAG Falls Short

- **Simple factual queries:** 13.4% lower accuracy than vanilla RAG on Natural Questions benchmark
- **Time-sensitive queries:** 16.6% accuracy drop for questions requiring real-time knowledge
- **Knowledge graph coverage:** Only ~65% of answer entities exist in the constructed KG (HotpotQA/NQ datasets)
- **Latency:** Graph construction and community summarization add significant latency

### Relevance to NEXUS

NEXUS's legal investigation use case is **highly aligned with GraphRAG's strengths**:
- Multi-hop reasoning across people, organizations, financial transactions
- Corpus-wide pattern detection across 50K+ documents
- Relationship-centric queries ("Who is connected to whom through what?")
- Complex analytical questions that span multiple documents

NEXUS is **less affected by GraphRAG's weaknesses**:
- Simple factual queries are not the primary use case
- Legal documents are not typically time-sensitive in the same way as news
- NEXUS's existing entity extraction (GLiNER) may achieve better coverage than LLM-only extraction

---

## 5. Integration Approaches

### Option A: Full Microsoft GraphRAG Replacement (NOT Recommended)

Replace NEXUS's ingestion and query pipelines with Microsoft's `graphrag` library.

- **Pros:** Battle-tested, community-supported, includes benchmarking tools (BenchmarkQED)
- **Cons:** Would discard NEXUS's mature multi-modal pipeline, Celery orchestration, streaming, conversation memory, visual retrieval. Massive cost at scale. Monolithic replacement.

### Option B: Cherry-Pick GraphRAG Concepts into NEXUS (Recommended)

Add community detection and summarization to NEXUS's existing Neo4j graph:

1. **Community Detection on Neo4j**
   Run Leiden/Louvain community detection on the existing Neo4j graph using Neo4j Graph Data Science (GDS) library. This requires no re-indexing — it operates on entities and relationships NEXUS already extracts.

2. **Hierarchical Community Summaries**
   Generate LLM summaries for each detected community at 2–3 levels of granularity. Store summaries as new nodes in Neo4j linked to their constituent entities.

3. **Global Query Router**
   Add a new node to the LangGraph query pipeline that routes corpus-wide questions to community summaries rather than vector retrieval.

4. **Incremental Updates**
   When new documents are ingested, re-run community detection on affected subgraphs and regenerate relevant summaries.

**Estimated effort:** 2–3 weeks of development
**Estimated cost:** Community detection is free (Neo4j GDS). Community summarization cost depends on number of communities (typically 100–1000x fewer than documents), likely $100–$500 for initial generation.

### Option C: LazyGraphRAG Hybrid (Recommended Alternative)

Adopt LazyGraphRAG's query-time approach instead of pre-computing summaries:

1. **Community Detection on Neo4j** (same as Option B)
2. **Query-Time Summarization:** When a global query arrives, identify relevant communities via entity matching, extract claims from community members on-the-fly, rank by relevance
3. **No pre-computed summaries needed** — dramatically simpler pipeline

**Estimated effort:** 1–2 weeks of development
**Estimated cost:** Only LLM costs at query time, controlled by relevance budget parameter

### Option D: Neo4j GraphRAG Python Package

Neo4j offers its own `neo4j-graphrag` Python package that provides:
- Knowledge graph construction from unstructured data
- Graph traversal retrievers
- Text-to-Cypher generation
- Vector + graph hybrid retrieval

This integrates natively with NEXUS's existing Neo4j instance and could complement the current `graph_service.py`.

**Estimated effort:** 1 week for evaluation, 2 weeks for integration

---

## 6. Recommendation

### Primary Recommendation: Option B + C Hybrid

**Phase 1 (Quick Win — 1–2 weeks):**
- Add Neo4j GDS community detection to the post-ingestion pipeline
- Implement community-aware retrieval in the query graph (LazyGraphRAG style, query-time summarization)
- Add a "global query" classification in the existing `classify` node

**Phase 2 (If Phase 1 proves valuable — 2–3 weeks):**
- Pre-compute community summaries for the most stable/large communities
- Implement hierarchical navigation in the entity explorer UI
- Add incremental community update on document ingestion

**Phase 3 (Optional optimization):**
- Evaluate Neo4j's `neo4j-graphrag` package for additional retrieval strategies
- Benchmark with BenchmarkQED to measure improvement
- Consider Personalized PageRank for graph traversal ranking (research shows graph operators matter more than graph structure)

### What NOT To Do

- **Do not** replace the existing ingestion pipeline with Microsoft's `graphrag` library — NEXUS's pipeline is more capable (multi-modal, streaming, entity resolution)
- **Do not** run full GraphRAG indexing on the entire corpus — cost-prohibitive at 50K documents
- **Do not** abandon Neo4j for GraphRAG's default Parquet-based storage — Neo4j is the right choice for NEXUS's investigative queries
- **Do not** use LLM-only entity extraction (GraphRAG's approach) — NEXUS's GLiNER + selective LLM approach is more cost-efficient

---

## 7. Technical Implementation Notes

### Neo4j GDS Community Detection

```cypher
-- Project the entity graph
CALL gds.graph.project(
  'nexus-entities',
  ['Person', 'Organization', 'Location', 'Financial'],
  {
    ASSOCIATED_WITH: {orientation: 'UNDIRECTED'},
    EMPLOYED_BY: {orientation: 'UNDIRECTED'},
    PAID: {orientation: 'UNDIRECTED'}
  }
)

-- Run Leiden community detection
CALL gds.leiden.write('nexus-entities', {
  writeProperty: 'communityId',
  maxLevels: 3,
  gamma: 1.0
})
```

### New LangGraph Node (Conceptual)

```python
async def global_query_handler(state: InvestigationState) -> dict:
    """Route global queries to community summaries."""
    if state.query_type != "global":
        return state

    # Get relevant communities from Neo4j
    communities = await graph_service.get_relevant_communities(
        entities=state.extracted_entities
    )

    # LazyGraphRAG: summarize relevant communities at query time
    community_context = await summarize_communities(
        communities, state.rewritten_query, budget=state.relevance_budget
    )

    state.context.append(community_context)
    return state
```

### Dependencies to Add

```toml
# pyproject.toml additions
# Neo4j GDS (for community detection)
graphdatascience = ">=1.7"
```

---

## 8. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Community detection quality on sparse graph | Medium | Medium | Start with well-connected entity types; tune Leiden parameters |
| LLM summarization cost for large communities | Low | Medium | LazyGraphRAG query-time approach; set budget limits |
| Neo4j GDS licensing (Enterprise vs. Community) | Medium | High | Verify GDS availability on Neo4j Community; consider alternatives (NetworkX for community detection) |
| Incremental update complexity | Medium | Low | Batch re-detection periodically rather than real-time |
| Integration with existing LangGraph pipeline | Low | Low | Additive change — new node in existing graph, no modifications to current nodes |

---

## Sources

- [Microsoft GraphRAG Project](https://www.microsoft.com/en-us/research/project/graphrag/)
- [Microsoft GraphRAG GitHub](https://github.com/microsoft/graphrag)
- [LazyGraphRAG Blog Post](https://www.microsoft.com/en-us/research/blog/lazygraphrag-setting-a-new-standard-for-quality-and-cost/)
- [GraphRAG Costs Explained (Microsoft)](https://techcommunity.microsoft.com/blog/azure-ai-foundry-blog/graphrag-costs-explained-what-you-need-to-know/4207978)
- [RAG vs. GraphRAG: Systematic Evaluation (arXiv)](https://arxiv.org/abs/2502.11371)
- [GraphRAG Accuracy Benchmark (FalkorDB)](https://www.falkordb.com/blog/graphrag-accuracy-diffbot-falkordb/)
- [Neo4j GraphRAG Developer Guide](https://neo4j.com/developer/genai-ecosystem/)
- [Qdrant + Neo4j GraphRAG Integration](https://qdrant.tech/documentation/examples/graphrag-qdrant-neo4j/)
- [GraphRAG Complete Guide 2026 (Meilisearch)](https://www.meilisearch.com/blog/graph-rag)
- [BenchmarkQED (Microsoft)](https://www.microsoft.com/en-us/research/blog/benchmarkqed-automated-benchmarking-of-rag-systems/)
- [Neo4j GraphAcademy - Knowledge Graph & GraphRAG Courses](https://graphacademy.neo4j.com/knowledge-graph-rag/)
- [DataStax LazyGraphRAG in LangChain](https://datastax.github.io/graph-rag/examples/lazy-graph-rag/)
- [Reduce GraphRAG Indexing Costs (FalkorDB)](https://www.falkordb.com/blog/reduce-graphrag-indexing-costs/)
- [Enterprise RAG Evolution 2026-2030 (NStarX)](https://nstarxinc.com/blog/the-next-frontier-of-rag-how-enterprise-knowledge-systems-will-evolve-2026-2030/)
