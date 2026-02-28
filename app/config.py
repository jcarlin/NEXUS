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
    enable_visual_embeddings: bool = False  # ColQwen2.5 deferred

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

    # --- Audit (SOC 2) ---
    audit_retention_days: int = 365
    enable_ai_audit_logging: bool = True

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
