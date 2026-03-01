"""Application configuration loaded from environment variables via Pydantic Settings."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """All NEXUS configuration. Values come from environment / .env file.

    Defaults are tuned for local dev on Apple Silicon (infra in Docker on localhost).
    """

    # --- LLM Providers ---
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    llm_provider: str = "anthropic"  # anthropic | openai | vllm
    llm_model: str = "claude-sonnet-4-5-20250929"
    vllm_base_url: str = "http://localhost:8080/v1"

    # --- Embedding ---
    embedding_provider: str = "openai"  # openai | local
    embedding_model: str = "text-embedding-3-large"
    embedding_dimensions: int = 1024
    local_embedding_model: str = "BAAI/bge-large-en-v1.5"
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

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }
