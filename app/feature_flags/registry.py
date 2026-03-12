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
