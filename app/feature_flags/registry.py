"""Static metadata registry for all feature flags.

Each entry maps a Settings attribute name (``enable_*``) to display metadata,
category, risk level, and DI caches that must be cleared on toggle.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.feature_flags.schemas import FlagCategory, FlagRiskLevel


@dataclass(frozen=True, slots=True)
class FlagMeta:
    display_name: str
    description: str
    category: FlagCategory
    risk_level: FlagRiskLevel
    di_caches: list[str] = field(default_factory=list)


FLAG_REGISTRY: dict[str, FlagMeta] = {
    # --- Retrieval & Embedding ---
    "enable_reranker": FlagMeta(
        display_name="Cross-Encoder Reranker",
        description="BGE reranker v2 for cross-encoder reranking of retrieval results.",
        category=FlagCategory.RETRIEVAL,
        risk_level=FlagRiskLevel.CACHE_CLEAR,
        di_caches=["get_reranker", "get_retriever", "get_query_graph"],
    ),
    "enable_sparse_embeddings": FlagMeta(
        display_name="Sparse Embeddings (BM42)",
        description="BM42 sparse vectors for hybrid dense+sparse retrieval via Qdrant native RRF.",
        category=FlagCategory.RETRIEVAL,
        risk_level=FlagRiskLevel.CACHE_CLEAR,
        di_caches=["get_sparse_embedder", "get_retriever"],
    ),
    "enable_visual_embeddings": FlagMeta(
        display_name="Visual Embeddings (ColQwen2.5)",
        description="ColQwen2.5 visual embedding and reranking for PDF pages. Loads a 3B-parameter model.",
        category=FlagCategory.RETRIEVAL,
        risk_level=FlagRiskLevel.CACHE_CLEAR,
        di_caches=["get_visual_embedder", "get_retriever", "get_query_graph"],
    ),
    "enable_retrieval_grading": FlagMeta(
        display_name="Retrieval Grading (CRAG)",
        description="CRAG-style relevance grading: heuristic scoring + conditional LLM grading for low-confidence retrievals.",
        category=FlagCategory.RETRIEVAL,
        risk_level=FlagRiskLevel.SAFE,
    ),
    # --- Query Pipeline ---
    "enable_agentic_pipeline": FlagMeta(
        display_name="Agentic Query Pipeline",
        description="Agentic LangGraph query pipeline with tool-use loop. Disabling falls back to v1 linear chain.",
        category=FlagCategory.QUERY,
        risk_level=FlagRiskLevel.CACHE_CLEAR,
        di_caches=["get_query_graph"],
    ),
    "enable_citation_verification": FlagMeta(
        display_name="Citation Verification",
        description="Self-RAG citation verification in query synthesis. Verifies claims against source chunks.",
        category=FlagCategory.QUERY,
        risk_level=FlagRiskLevel.SAFE,
    ),
    # --- Entity & Graph ---
    "enable_relationship_extraction": FlagMeta(
        display_name="LLM Relationship Extraction",
        description="Instructor + LLM-based relationship extraction from entity-rich chunks during ingestion.",
        category=FlagCategory.ENTITY_GRAPH,
        risk_level=FlagRiskLevel.SAFE,
    ),
    "enable_coreference_resolution": FlagMeta(
        display_name="Coreference Resolution",
        description="spaCy + coreferee pronoun resolution during entity resolution. Loads en_core_web_lg (~560 MB).",
        category=FlagCategory.ENTITY_GRAPH,
        risk_level=FlagRiskLevel.CACHE_CLEAR,
        di_caches=["get_coref_resolver"],
    ),
    "enable_graph_centrality": FlagMeta(
        display_name="Graph Centrality Metrics",
        description="Neo4j GDS centrality metrics (degree, PageRank, betweenness) on the entity graph.",
        category=FlagCategory.ENTITY_GRAPH,
        risk_level=FlagRiskLevel.SAFE,
    ),
    "enable_near_duplicate_detection": FlagMeta(
        display_name="Near-Duplicate Detection",
        description="MinHash-based near-duplicate and document version detection during ingestion.",
        category=FlagCategory.INGESTION,
        risk_level=FlagRiskLevel.CACHE_CLEAR,
        di_caches=["get_dedup_detector"],
    ),
    # --- Ingestion Pipeline ---
    "enable_email_threading": FlagMeta(
        display_name="Email Threading",
        description="Reconstruct email conversation threads from In-Reply-To and References headers.",
        category=FlagCategory.INGESTION,
        risk_level=FlagRiskLevel.SAFE,
    ),
    "enable_hot_doc_detection": FlagMeta(
        display_name="Hot Doc Detection",
        description="Sentiment/significance scoring to flag key documents during ingestion.",
        category=FlagCategory.INGESTION,
        risk_level=FlagRiskLevel.SAFE,
    ),
    "enable_chunk_quality_scoring": FlagMeta(
        display_name="Chunk Quality Scoring",
        description="Heuristic quality scoring for each chunk during ingestion (~5ms/chunk, no model).",
        category=FlagCategory.INGESTION,
        risk_level=FlagRiskLevel.SAFE,
    ),
    "enable_contextual_chunks": FlagMeta(
        display_name="Contextual Chunk Enrichment",
        description="LLM-generated contextual prefixes prepended to chunks before embedding for better retrieval.",
        category=FlagCategory.INGESTION,
        risk_level=FlagRiskLevel.SAFE,
    ),
    # --- Intelligence ---
    "enable_case_setup_agent": FlagMeta(
        display_name="Case Setup Agent",
        description="Pre-populate query context from case/matter metadata before query execution.",
        category=FlagCategory.INTELLIGENCE,
        risk_level=FlagRiskLevel.SAFE,
    ),
    "enable_topic_clustering": FlagMeta(
        display_name="Topic Clustering (BERTopic)",
        description="BERTopic-based topic clustering of document chunks. Loads all-MiniLM-L6-v2 (~80 MB).",
        category=FlagCategory.INTELLIGENCE,
        risk_level=FlagRiskLevel.SAFE,
    ),
    # --- Audit & Compliance ---
    "enable_ai_audit_logging": FlagMeta(
        display_name="AI Audit Logging",
        description="Log all LLM calls to ai_audit_log table for SOC 2 compliance and cost tracking.",
        category=FlagCategory.AUDIT,
        risk_level=FlagRiskLevel.SAFE,
    ),
    "enable_redaction": FlagMeta(
        display_name="PII Redaction Engine",
        description="PII detection and document redaction via GLiNER + PDF manipulation.",
        category=FlagCategory.AUDIT,
        risk_level=FlagRiskLevel.SAFE,
    ),
    # --- Integrations (restart-required) ---
    "enable_google_drive": FlagMeta(
        display_name="Google Drive Connector",
        description="Google Drive OAuth connector for document ingestion. Router mounted at startup.",
        category=FlagCategory.INTEGRATIONS,
        risk_level=FlagRiskLevel.RESTART,
    ),
    "enable_sso": FlagMeta(
        display_name="SSO / OIDC Authentication",
        description="OpenID Connect SSO authentication. OIDC router mounted at startup.",
        category=FlagCategory.INTEGRATIONS,
        risk_level=FlagRiskLevel.RESTART,
    ),
    "enable_memo_drafting": FlagMeta(
        display_name="Memo Drafting",
        description="AI-assisted legal memo drafting module. Router mounted at startup.",
        category=FlagCategory.INTEGRATIONS,
        risk_level=FlagRiskLevel.RESTART,
    ),
    "enable_prometheus_metrics": FlagMeta(
        display_name="Prometheus Metrics",
        description="Prometheus metrics endpoint at /metrics. Instrumentator mounted at startup.",
        category=FlagCategory.INTEGRATIONS,
        risk_level=FlagRiskLevel.RESTART,
    ),
    "enable_batch_embeddings": FlagMeta(
        display_name="Batch Embeddings (Stub)",
        description="Async batch embedding API support. Currently a stub with no runtime effect.",
        category=FlagCategory.INTEGRATIONS,
        risk_level=FlagRiskLevel.RESTART,
    ),
    # --- Tier 1 Maturity flags ---
    "enable_multi_query_expansion": FlagMeta(
        display_name="Multi-Query Expansion",
        description="Generate 3-5 legal vocabulary reformulations per query for broader retrieval coverage.",
        category=FlagCategory.QUERY,
        risk_level=FlagRiskLevel.SAFE,
    ),
    "enable_text_to_cypher": FlagMeta(
        display_name="Text-to-Cypher Generation",
        description="Generate and execute read-only Cypher queries against the Neo4j knowledge graph from natural language.",
        category=FlagCategory.QUERY,
        risk_level=FlagRiskLevel.SAFE,
    ),
    "enable_prompt_routing": FlagMeta(
        display_name="Semantic Prompt Routing",
        description="Route queries to specialized system prompt addenda based on query type classification.",
        category=FlagCategory.QUERY,
        risk_level=FlagRiskLevel.SAFE,
    ),
    "enable_question_decomposition": FlagMeta(
        display_name="Question Decomposition",
        description="Decompose complex multi-part questions into sub-questions with independent retrieval.",
        category=FlagCategory.QUERY,
        risk_level=FlagRiskLevel.SAFE,
    ),
    # --- Tier 2 Maturity flags ---
    "enable_hyde": FlagMeta(
        display_name="HyDE (Hypothetical Document Embeddings)",
        description="Bridge vocabulary gap by embedding a hypothetical answer for dense retrieval instead of the raw query.",
        category=FlagCategory.QUERY,
        risk_level=FlagRiskLevel.SAFE,
    ),
    "enable_self_reflection": FlagMeta(
        display_name="Self-Reflection Loop",
        description="Re-investigate flagged claims when citation faithfulness falls below threshold (max 1 retry).",
        category=FlagCategory.QUERY,
        risk_level=FlagRiskLevel.SAFE,
    ),
    "enable_text_to_sql": FlagMeta(
        display_name="Text-to-SQL Generation",
        description="Generate and execute read-only SQL queries against the relational schema from natural language.",
        category=FlagCategory.QUERY,
        risk_level=FlagRiskLevel.SAFE,
    ),
    "enable_document_summarization": FlagMeta(
        display_name="Document Summarization",
        description="Generate 2-3 sentence LLM summaries per document at ingestion time.",
        category=FlagCategory.INGESTION,
        risk_level=FlagRiskLevel.SAFE,
    ),
    "enable_multi_representation": FlagMeta(
        display_name="Multi-Representation Indexing",
        description="Store chunk summaries as a third named vector for triple RRF fusion (dense + sparse + summary).",
        category=FlagCategory.INGESTION,
        risk_level=FlagRiskLevel.CACHE_CLEAR,
        di_caches=["get_vector_store", "get_retriever"],
    ),
    "enable_production_quality_monitoring": FlagMeta(
        display_name="Production Quality Monitoring",
        description="Score sampled production queries for retrieval relevance and generation faithfulness.",
        category=FlagCategory.QUERY,
        risk_level=FlagRiskLevel.SAFE,
    ),
    # --- Tier 3 Maturity flags ---
    "enable_adaptive_retrieval_depth": FlagMeta(
        display_name="Adaptive Retrieval Depth",
        description="Query-type-dependent retrieval depth (factual=15, analytical=30, exploratory=40, etc.).",
        category=FlagCategory.RETRIEVAL,
        risk_level=FlagRiskLevel.SAFE,
    ),
    "enable_auto_graph_routing": FlagMeta(
        display_name="Automatic Graph Routing",
        description="Route simple factual queries to V1 (faster) and complex queries to agentic graph automatically.",
        category=FlagCategory.QUERY,
        risk_level=FlagRiskLevel.SAFE,
    ),
    "enable_ocr_correction": FlagMeta(
        display_name="OCR Error Correction",
        description="Regex-based ligature and legal term correction for scanned documents, with optional LLM cleanup.",
        category=FlagCategory.INGESTION,
        risk_level=FlagRiskLevel.SAFE,
    ),
    "enable_data_retention": FlagMeta(
        display_name="Data Retention Policies",
        description="Configurable per-matter data retention with automated purge after retention period.",
        category=FlagCategory.AUDIT,
        risk_level=FlagRiskLevel.SAFE,
    ),
    "enable_saml": FlagMeta(
        display_name="SAML Authentication",
        description="SAML 2.0 SSO authentication for enterprise identity providers.",
        category=FlagCategory.INTEGRATIONS,
        risk_level=FlagRiskLevel.RESTART,
    ),
    "enable_splade_sparse": FlagMeta(
        display_name="SPLADE Sparse Retrieval",
        description="Learned sparse embeddings (SPLADE v3) with query expansion for legal vocabulary, replacing BM42.",
        category=FlagCategory.RETRIEVAL,
        risk_level=FlagRiskLevel.CACHE_CLEAR,
        di_caches=["get_sparse_embedder", "get_retriever", "get_query_graph"],
    ),
    "enable_deposition_prep": FlagMeta(
        display_name="Deposition Prep Workflow",
        description="AI-assisted deposition preparation with witness profiling and question generation.",
        category=FlagCategory.INTELLIGENCE,
        risk_level=FlagRiskLevel.RESTART,
    ),
    "enable_document_comparison": FlagMeta(
        display_name="Document Comparison / Redline",
        description="Side-by-side diff of document versions with change highlighting.",
        category=FlagCategory.INTELLIGENCE,
        risk_level=FlagRiskLevel.SAFE,
    ),
    "enable_hallugraph_alignment": FlagMeta(
        display_name="HalluGraph Entity-Graph Alignment",
        description="Post-generation check — extract entities from LLM response, verify each exists in Neo4j KG, flag hallucinated entities.",
        category=FlagCategory.QUERY,
        risk_level=FlagRiskLevel.SAFE,
    ),
    "enable_graphrag_communities": FlagMeta(
        display_name="GraphRAG Community Summaries",
        description="Neo4j GDS Louvain community detection with LLM-generated summaries for entity clusters.",
        category=FlagCategory.ENTITY_GRAPH,
        risk_level=FlagRiskLevel.SAFE,
    ),
    "enable_service_operations": FlagMeta(
        display_name="Service Operations",
        description="Docker container management, Celery worker control, and uptime monitoring admin panel.",
        category=FlagCategory.INTEGRATIONS,
        risk_level=FlagRiskLevel.RESTART,
        di_caches=["get_docker"],
    ),
}


def validate_registry() -> None:
    """Verify all registry entries map to real Settings attributes.

    Called at import time to catch stale entries early.
    """
    from app.config import Settings

    settings_fields = set(Settings.model_fields.keys())
    for flag_name in FLAG_REGISTRY:
        if flag_name not in settings_fields:
            raise ValueError(f"FLAG_REGISTRY key '{flag_name}' not found in Settings")


validate_registry()
