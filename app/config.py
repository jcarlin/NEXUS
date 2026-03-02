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
    public_endpoint: str
    access_key: str
    secret_key: str
    bucket: str
    use_ssl: bool


class RetrievalConfig(BaseModel):
    text_limit: int
    graph_limit: int
    prefetch_multiplier: int
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


class Settings(BaseSettings):
    """All NEXUS configuration. Values come from environment / .env file.

    Defaults are tuned for local dev on Apple Silicon (infra in Docker on localhost).
    """

    # --- LLM Providers ---
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    llm_provider: str = "anthropic"  # anthropic | openai | vllm | ollama
    llm_model: str = "claude-sonnet-4-5-20250929"
    vllm_base_url: str = "http://localhost:8080/v1"
    ollama_base_url: str = "http://localhost:11434/v1"

    # --- Embedding ---
    embedding_provider: str = "openai"  # openai | local | tei
    embedding_model: str = "text-embedding-3-large"
    embedding_dimensions: int = 1024
    local_embedding_model: str = "BAAI/bge-large-en-v1.5"
    tei_embedding_url: str = "http://localhost:8081"
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
    minio_public_endpoint: str = ""  # Public-facing endpoint for presigned URLs (cloud deploy)
    minio_access_key: str = "nexus-admin"
    minio_secret_key: str = "changeme"
    minio_bucket: str = "documents"
    minio_use_ssl: bool = False

    # --- Processing ---
    celery_concurrency: int = 1
    chunk_size: int = 512
    chunk_overlap: int = 64
    gliner_model: str = "urchade/gliner_multi_pii-v1"
    enable_relationship_extraction: bool = False  # Tier-2 Instructor+LLM extraction off by default

    # --- Rate Limiting ---
    rate_limit_queries_per_minute: int = 30
    rate_limit_ingests_per_minute: int = 10

    # --- Embedding ---
    embedding_batch_size: int = 32  # Conservative for 16GB Mac

    # --- Retrieval Tuning ---
    retrieval_text_limit: int = 20
    retrieval_graph_limit: int = 20
    retrieval_prefetch_multiplier: int = 2
    query_entity_threshold: float = 0.5

    # --- Reranker ---
    enable_reranker: bool = False  # bge-reranker-v2-m3, deferred
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
    enable_near_duplicate_detection: bool = False
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

    # --- Redaction ---
    enable_redaction: bool = False

    # --- Export ---
    export_max_documents: int = 10000

    # --- Citation Verification ---
    max_claims_to_verify: int = 10

    # --- Agentic Pipeline ---
    enable_agentic_pipeline: bool = True
    enable_citation_verification: bool = True
    agentic_recursion_limit_fast: int = 6
    agentic_recursion_limit_standard: int = 12
    agentic_recursion_limit_deep: int = 20

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
                public_endpoint=self.minio_public_endpoint,
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
            )
        return self
