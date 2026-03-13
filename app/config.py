"""Application configuration loaded from environment variables via Pydantic Settings."""

from pydantic import BaseModel, model_validator
from pydantic_settings import BaseSettings

# --- Nested config groups (read-only views over flat fields) ---


class LLMConfig(BaseModel):
    provider: str
    model: str
    anthropic_api_key: str
    openai_api_key: str
    vllm_base_url: str
    ollama_base_url: str


class EmbeddingConfig(BaseModel):
    provider: str
    model: str
    dimensions: int
    local_model: str
    batch_size: int
    tei_url: str
    ollama_model: str
    ollama_base_url: str
    enable_visual: bool
    visual_model: str
    visual_device: str
    visual_batch_size: int
    visual_dim: int
    visual_rerank_weight: float
    visual_rerank_top_n: int
    visual_page_dpi: int


class DatabaseConfig(BaseModel):
    postgres_url: str
    postgres_url_sync: str
    redis_url: str
    qdrant_url: str
    neo4j_uri: str
    neo4j_user: str
    neo4j_password: str


class StorageConfig(BaseModel):
    endpoint: str
    access_key: str
    secret_key: str
    bucket: str
    use_ssl: bool


class RetrievalConfig(BaseModel):
    text_limit: int
    graph_limit: int
    prefetch_multiplier: int
    dense_prefetch_multiplier: int
    sparse_prefetch_multiplier: int
    entity_threshold: float
    enable_reranker: bool
    reranker_model: str
    reranker_top_n: int
    reranker_provider: str
    tei_reranker_url: str


class AuthConfig(BaseModel):
    jwt_secret_key: str
    jwt_algorithm: str
    jwt_access_token_expire_minutes: int
    jwt_refresh_token_expire_days: int
    cors_allowed_origins: str
    require_matter_header: bool


class ProcessingConfig(BaseModel):
    celery_concurrency: int
    chunk_size: int
    chunk_overlap: int
    gliner_model: str
    enable_relationship_extraction: bool


class FeatureFlags(BaseModel):
    visual_embeddings: bool
    relationship_extraction: bool
    reranker: bool
    sparse_embeddings: bool
    email_threading: bool
    near_duplicate_detection: bool
    ai_audit_logging: bool
    batch_embeddings: bool
    case_setup_agent: bool
    coreference_resolution: bool
    graph_centrality: bool
    hot_doc_detection: bool
    topic_clustering: bool
    agentic_pipeline: bool
    citation_verification: bool
    redaction: bool
    google_drive: bool
    prometheus_metrics: bool
    sso: bool
    saml: bool
    memo_drafting: bool
    chunk_quality_scoring: bool
    contextual_chunks: bool
    retrieval_grading: bool
    multi_query_expansion: bool
    text_to_cypher: bool
    prompt_routing: bool
    question_decomposition: bool
    data_retention: bool
    hyde: bool
    self_reflection: bool
    text_to_sql: bool
    document_summarization: bool
    multi_representation: bool
    production_quality_monitoring: bool
    auto_graph_routing: bool
    adaptive_retrieval_depth: bool
    ocr_correction: bool


class Settings(BaseSettings):
    """All NEXUS configuration. Values come from environment / .env file.

    Defaults are tuned for local dev on Apple Silicon (infra in Docker on localhost).
    """

    # --- LLM Providers ---
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    gemini_api_key: str = ""
    llm_provider: str = "anthropic"  # anthropic | openai | vllm | ollama
    llm_model: str = "claude-sonnet-4-5-20250929"
    query_llm_model: str = ""  # Query pipeline model; falls back to llm_model if empty
    vllm_base_url: str = "http://localhost:8080/v1"
    ollama_base_url: str = "http://localhost:11434/v1"

    # --- Embedding ---
    embedding_provider: str = "openai"  # openai | local | tei | gemini | ollama
    embedding_model: str = "text-embedding-3-large"
    gemini_embedding_model: str = "gemini-embedding-exp-03-07"
    embedding_dimensions: int = 1024
    local_embedding_model: str = "BAAI/bge-large-en-v1.5"
    tei_embedding_url: str = "http://localhost:8081"
    ollama_embedding_model: str = "nomic-embed-text"
    enable_visual_embeddings: bool = False  # ColQwen2.5 visual reranking
    visual_embedding_model: str = "vidore/colqwen2.5-v0.2"
    visual_embedding_device: str = "mps"  # mps | cuda | cpu
    visual_embedding_batch_size: int = 4  # 3B param model, small batches
    visual_embedding_dim: int = 128  # Per-token dimension
    visual_rerank_weight: float = 0.3  # Blend factor for score fusion
    visual_rerank_top_n: int = 20  # Candidates to visually rerank
    visual_page_dpi: int = 144  # DPI for PDF page rendering

    # --- PostgreSQL ---
    postgres_url: str = "postgresql+asyncpg://nexus:changeme@localhost:5432/nexus"
    postgres_url_sync: str = "postgresql://nexus:changeme@localhost:5432/nexus"  # For alembic

    # --- Redis ---
    redis_url: str = "redis://localhost:6379/0"

    # --- Qdrant ---
    qdrant_url: str = "http://localhost:6333"

    # --- Neo4j ---
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "changeme"

    # --- MinIO (S3-compatible) ---
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "nexus-admin"
    minio_secret_key: str = "changeme"
    minio_bucket: str = "documents"
    minio_use_ssl: bool = False
    minio_webhook_secret: str = ""  # Shared secret for MinIO webhook signature verification

    # --- Processing ---
    celery_concurrency: int = 1
    chunk_size: int = 512
    chunk_overlap: int = 64
    gliner_model: str = "urchade/gliner_multi_pii-v1"
    enable_relationship_extraction: bool = False  # Tier-2 Instructor+LLM extraction off by default

    # --- Rate Limiting ---
    rate_limit_queries_per_minute: int = 30
    rate_limit_ingests_per_minute: int = 10

    # --- Chunk Quality Scoring ---
    enable_chunk_quality_scoring: bool = False

    # --- Contextual Chunk Enrichment ---
    enable_contextual_chunks: bool = False
    contextual_chunk_model: str = ""  # Falls back to llm_model if empty
    contextual_chunk_max_tokens: int = 100
    contextual_chunk_batch_size: int = 20  # Chunks per LLM call
    contextual_chunk_concurrency: int = 4  # Concurrent batches

    # --- Matryoshka Dimensionality Optimization (T3-15) ---
    matryoshka_search_dimensions: int = 0  # 0 = disabled; e.g. 256, 512 for smaller query vectors

    # --- Embedding ---
    embedding_batch_size: int = 32  # Conservative for 16GB Mac

    # --- Retrieval Tuning ---
    retrieval_text_limit: int = 40
    retrieval_graph_limit: int = 20
    retrieval_prefetch_multiplier: int = 2
    query_entity_threshold: float = 0.5

    # --- Reranker ---
    enable_reranker: bool = True  # bge-reranker-v2-m3
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    reranker_top_n: int = 10
    reranker_provider: str = "local"  # local | tei
    tei_reranker_url: str = "http://localhost:8082"

    # --- Sparse Embeddings ---
    enable_sparse_embeddings: bool = False
    sparse_embedding_model: str = "Qdrant/bm42-all-minilm-l6-v2-attentions"

    # --- Email Threading ---
    enable_email_threading: bool = True

    # --- Near-Duplicate Detection ---
    enable_near_duplicate_detection: bool = True
    dedup_jaccard_threshold: float = 0.80
    dedup_num_permutations: int = 128
    dedup_shingle_size: int = 5
    dedup_version_upper_threshold: float = 0.95

    # --- Audit (SOC 2) ---
    audit_retention_days: int = 365
    enable_ai_audit_logging: bool = True

    # --- Batch Embeddings (stub — real-time embedding used for now) ---
    enable_batch_embeddings: bool = False
    batch_embeddings_poll_interval: int = 60

    # --- Case Intelligence ---
    enable_case_setup_agent: bool = False

    # --- Coreference Resolution (M11) ---
    enable_coreference_resolution: bool = False  # spaCy + coreferee
    coreference_model: str = "en_core_web_lg"

    # --- Graph Centrality (M11) ---
    enable_graph_centrality: bool = False  # Neo4j GDS betweenness/PageRank

    # --- Hot Doc Detection (M10b) ---
    enable_hot_doc_detection: bool = False
    hot_doc_score_threshold: float = 0.6

    # --- Communication Analytics (M10c) ---
    enable_topic_clustering: bool = False
    bertopic_embedding_model: str = "all-MiniLM-L6-v2"
    bertopic_min_cluster_size: int = 5

    # --- Google Drive ---
    enable_google_drive: bool = False
    gdrive_client_id: str = ""
    gdrive_client_secret: str = ""
    gdrive_redirect_uri: str = "http://localhost:5173/gdrive/callback"
    gdrive_encryption_key: str = ""  # Fernet key for encrypting OAuth tokens at rest
    gdrive_max_concurrent_downloads: int = 10

    # --- Redaction ---
    enable_redaction: bool = False

    # --- Prometheus Metrics ---
    enable_prometheus_metrics: bool = True

    # --- Memo Drafting ---
    enable_memo_drafting: bool = False

    # --- SSO / OIDC ---
    enable_sso: bool = False
    oidc_provider_name: str = "SSO"  # Display name for UI button
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    oidc_issuer_url: str = ""  # e.g. https://accounts.google.com
    oidc_redirect_uri: str = "http://localhost:5173/auth/oidc/callback"
    oidc_role_mapping: str = ""  # JSON: {"admin_group": "admin", "attorney_group": "attorney"}
    oidc_default_role: str = "reviewer"  # Role for users with no group mapping

    # --- SSO / SAML ---
    enable_saml: bool = False
    saml_entity_id: str = ""  # SP entity ID (e.g. https://nexus.example.com/saml)
    saml_idp_metadata_url: str = ""  # IdP metadata URL (optional, for auto-config)
    saml_idp_sso_url: str = ""  # IdP SSO endpoint
    saml_idp_cert: str = ""  # IdP X.509 certificate (PEM, single line or base64)
    saml_sp_cert: str = ""  # SP X.509 certificate (optional, for signed requests)
    saml_sp_key: str = ""  # SP private key (optional, for signed requests)
    saml_role_mapping: str = "{}"  # JSON: {"admin_group": "admin", "attorney_group": "attorney"}
    saml_default_role: str = "viewer"  # Role for users with no group mapping

    # --- Export ---
    export_max_documents: int = 10000

    # --- Citation Verification ---
    max_claims_to_verify: int = 3

    # --- Retrieval Grading (CRAG) ---
    enable_retrieval_grading: bool = False

    # --- Multi-Query Expansion (T1-1) ---
    enable_multi_query_expansion: bool = False
    multi_query_count: int = 3

    # --- Text-to-Cypher Generation (T1-2) ---
    enable_text_to_cypher: bool = False

    # --- Semantic Prompt Routing (T1-6) ---
    enable_prompt_routing: bool = False

    # --- Question Decomposition (T1-10) ---
    enable_question_decomposition: bool = False

    # --- Adaptive Retrieval Depth (T3-13) ---
    enable_adaptive_retrieval_depth: bool = False
    retrieval_depth_factual_text: int = 15
    retrieval_depth_factual_graph: int = 8
    retrieval_depth_analytical_text: int = 30
    retrieval_depth_analytical_graph: int = 15
    retrieval_depth_comparative_text: int = 35
    retrieval_depth_comparative_graph: int = 20
    retrieval_depth_temporal_text: int = 25
    retrieval_depth_temporal_graph: int = 12
    retrieval_depth_procedural_text: int = 20
    retrieval_depth_procedural_graph: int = 10
    retrieval_depth_exploratory_text: int = 40
    retrieval_depth_exploratory_graph: int = 20

    # --- OCR Error Correction (T3-14) ---
    enable_ocr_correction: bool = False
    ocr_correction_use_llm: bool = False  # LLM-assisted correction (expensive)

    # --- HyDE (Hypothetical Document Embeddings) (T2-6) ---
    enable_hyde: bool = False
    hyde_model: str = ""  # Falls back to llm_model if empty

    # --- Self-Reflection Loop (T2-8) ---
    enable_self_reflection: bool = False
    self_reflection_faithfulness_threshold: float = 0.8
    self_reflection_max_retries: int = 1

    # --- RRF Per-Modality Prefetch Multipliers (T2-9) ---
    retrieval_dense_prefetch_multiplier: int = 2
    retrieval_sparse_prefetch_multiplier: int = 2

    # --- Text-to-SQL Generation (T2-10) ---
    enable_text_to_sql: bool = False

    # --- Document Summarization (T2-12) ---
    enable_document_summarization: bool = False

    # --- Multi-Representation Indexing (T2-11) ---
    enable_multi_representation: bool = False
    multi_representation_concurrency: int = 4

    # --- Production Quality Monitoring (T2-5) ---
    enable_production_quality_monitoring: bool = False
    quality_monitoring_sample_rate: float = 0.1

    # --- Data Retention ---
    enable_data_retention: bool = False
    grading_model: str = ""  # Falls back to llm_model if empty
    grading_confidence_threshold: float = 0.5  # Median score below this triggers LLM grading

    # --- Agentic Pipeline ---
    enable_agentic_pipeline: bool = True
    enable_citation_verification: bool = True
    # --- Automatic Graph Routing (T3-12) ---
    enable_auto_graph_routing: bool = False
    agentic_recursion_limit_fast: int = 24
    agentic_recursion_limit_standard: int = 40
    agentic_recursion_limit_deep: int = 60

    # --- LangSmith Tracing ---
    langchain_tracing_v2: bool = False
    langchain_api_key: str = ""
    langchain_project: str = "nexus"

    # --- Logging ---
    log_level: str = "INFO"  # DEBUG | INFO | WARNING | ERROR | CRITICAL

    # --- Auth ---
    jwt_secret_key: str = "change-me-to-a-random-64-char-string"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7
    cors_allowed_origins: str = "http://localhost:5173,http://localhost:3000"
    require_matter_header: bool = True

    # --- Nested config groups (populated from flat fields via validator) ---
    llm: LLMConfig | None = None
    embedding: EmbeddingConfig | None = None
    database: DatabaseConfig | None = None
    storage: StorageConfig | None = None
    retrieval: RetrievalConfig | None = None
    auth: AuthConfig | None = None
    processing: ProcessingConfig | None = None
    features: FeatureFlags | None = None

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    @model_validator(mode="after")
    def _populate_nested(self) -> "Settings":
        if self.llm is None:
            self.llm = LLMConfig(
                provider=self.llm_provider,
                model=self.llm_model,
                anthropic_api_key=self.anthropic_api_key,
                openai_api_key=self.openai_api_key,
                vllm_base_url=self.vllm_base_url,
                ollama_base_url=self.ollama_base_url,
            )
        if self.embedding is None:
            self.embedding = EmbeddingConfig(
                provider=self.embedding_provider,
                model=self.embedding_model,
                dimensions=self.embedding_dimensions,
                local_model=self.local_embedding_model,
                batch_size=self.embedding_batch_size,
                tei_url=self.tei_embedding_url,
                ollama_model=self.ollama_embedding_model,
                ollama_base_url=self.ollama_base_url.removesuffix("/v1"),
                enable_visual=self.enable_visual_embeddings,
                visual_model=self.visual_embedding_model,
                visual_device=self.visual_embedding_device,
                visual_batch_size=self.visual_embedding_batch_size,
                visual_dim=self.visual_embedding_dim,
                visual_rerank_weight=self.visual_rerank_weight,
                visual_rerank_top_n=self.visual_rerank_top_n,
                visual_page_dpi=self.visual_page_dpi,
            )
        if self.database is None:
            self.database = DatabaseConfig(
                postgres_url=self.postgres_url,
                postgres_url_sync=self.postgres_url_sync,
                redis_url=self.redis_url,
                qdrant_url=self.qdrant_url,
                neo4j_uri=self.neo4j_uri,
                neo4j_user=self.neo4j_user,
                neo4j_password=self.neo4j_password,
            )
        if self.storage is None:
            self.storage = StorageConfig(
                endpoint=self.minio_endpoint,
                access_key=self.minio_access_key,
                secret_key=self.minio_secret_key,
                bucket=self.minio_bucket,
                use_ssl=self.minio_use_ssl,
            )
        if self.retrieval is None:
            self.retrieval = RetrievalConfig(
                text_limit=self.retrieval_text_limit,
                graph_limit=self.retrieval_graph_limit,
                prefetch_multiplier=self.retrieval_prefetch_multiplier,
                dense_prefetch_multiplier=self.retrieval_dense_prefetch_multiplier,
                sparse_prefetch_multiplier=self.retrieval_sparse_prefetch_multiplier,
                entity_threshold=self.query_entity_threshold,
                enable_reranker=self.enable_reranker,
                reranker_model=self.reranker_model,
                reranker_top_n=self.reranker_top_n,
                reranker_provider=self.reranker_provider,
                tei_reranker_url=self.tei_reranker_url,
            )
        if self.auth is None:
            self.auth = AuthConfig(
                jwt_secret_key=self.jwt_secret_key,
                jwt_algorithm=self.jwt_algorithm,
                jwt_access_token_expire_minutes=self.jwt_access_token_expire_minutes,
                jwt_refresh_token_expire_days=self.jwt_refresh_token_expire_days,
                cors_allowed_origins=self.cors_allowed_origins,
                require_matter_header=self.require_matter_header,
            )
        if self.processing is None:
            self.processing = ProcessingConfig(
                celery_concurrency=self.celery_concurrency,
                chunk_size=self.chunk_size,
                chunk_overlap=self.chunk_overlap,
                gliner_model=self.gliner_model,
                enable_relationship_extraction=self.enable_relationship_extraction,
            )
        if self.features is None:
            self.features = FeatureFlags(
                visual_embeddings=self.enable_visual_embeddings,
                relationship_extraction=self.enable_relationship_extraction,
                reranker=self.enable_reranker,
                sparse_embeddings=self.enable_sparse_embeddings,
                email_threading=self.enable_email_threading,
                near_duplicate_detection=self.enable_near_duplicate_detection,
                ai_audit_logging=self.enable_ai_audit_logging,
                batch_embeddings=self.enable_batch_embeddings,
                case_setup_agent=self.enable_case_setup_agent,
                coreference_resolution=self.enable_coreference_resolution,
                graph_centrality=self.enable_graph_centrality,
                hot_doc_detection=self.enable_hot_doc_detection,
                topic_clustering=self.enable_topic_clustering,
                agentic_pipeline=self.enable_agentic_pipeline,
                citation_verification=self.enable_citation_verification,
                redaction=self.enable_redaction,
                google_drive=self.enable_google_drive,
                prometheus_metrics=self.enable_prometheus_metrics,
                sso=self.enable_sso,
                saml=self.enable_saml,
                memo_drafting=self.enable_memo_drafting,
                chunk_quality_scoring=self.enable_chunk_quality_scoring,
                contextual_chunks=self.enable_contextual_chunks,
                retrieval_grading=self.enable_retrieval_grading,
                multi_query_expansion=self.enable_multi_query_expansion,
                text_to_cypher=self.enable_text_to_cypher,
                prompt_routing=self.enable_prompt_routing,
                question_decomposition=self.enable_question_decomposition,
                data_retention=self.enable_data_retention,
                hyde=self.enable_hyde,
                self_reflection=self.enable_self_reflection,
                text_to_sql=self.enable_text_to_sql,
                document_summarization=self.enable_document_summarization,
                multi_representation=self.enable_multi_representation,
                production_quality_monitoring=self.enable_production_quality_monitoring,
                auto_graph_routing=self.enable_auto_graph_routing,
                adaptive_retrieval_depth=self.enable_adaptive_retrieval_depth,
                ocr_correction=self.enable_ocr_correction,
            )
        return self
