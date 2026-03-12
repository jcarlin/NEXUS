"""Tests for nested config grouping in Settings."""

from app.config import Settings


class TestNestedConfig:
    def test_flat_fields_still_work(self):
        s = Settings(anthropic_api_key="k", openai_api_key="k")
        assert s.llm_provider == "anthropic"
        assert s.embedding_model == "text-embedding-3-large"
        assert s.chunk_size == 512

    def test_nested_llm_populated(self):
        s = Settings(anthropic_api_key="k", openai_api_key="k")
        assert s.llm is not None
        assert s.llm.provider == "anthropic"
        assert s.llm.model == s.llm_model
        assert s.llm.anthropic_api_key == "k"
        assert s.llm.openai_api_key == "k"
        assert s.llm.vllm_base_url == s.vllm_base_url

    def test_nested_llm_ollama_base_url_populated(self):
        s = Settings(anthropic_api_key="k", openai_api_key="k")
        assert s.llm.ollama_base_url == "http://localhost:11434/v1"

    def test_nested_database_populated(self):
        s = Settings(anthropic_api_key="k", openai_api_key="k")
        assert s.database is not None
        assert s.database.postgres_url == s.postgres_url
        assert s.database.postgres_url_sync == s.postgres_url_sync
        assert s.database.redis_url == s.redis_url
        assert s.database.qdrant_url == s.qdrant_url
        assert s.database.neo4j_uri == s.neo4j_uri

    def test_nested_features_populated(self, monkeypatch):
        monkeypatch.setenv("ENABLE_VISUAL_EMBEDDINGS", "false")
        monkeypatch.setenv("ENABLE_RELATIONSHIP_EXTRACTION", "false")
        monkeypatch.setenv("ENABLE_RERANKER", "false")
        s = Settings(anthropic_api_key="k", openai_api_key="k")
        assert s.features is not None
        assert s.features.visual_embeddings is False
        assert s.features.relationship_extraction is False
        assert s.features.reranker is False
        assert s.features.agentic_pipeline is True
        assert s.features.citation_verification is True
        assert s.features.email_threading is True

    def test_nested_storage_populated(self):
        s = Settings(anthropic_api_key="k", openai_api_key="k")
        assert s.storage is not None
        assert s.storage.bucket == "documents"
        assert s.storage.endpoint == "localhost:9000"
        assert s.storage.access_key == "nexus-admin"
        assert s.storage.use_ssl is False

    def test_env_override_propagates_to_nested(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        s = Settings(anthropic_api_key="k", openai_api_key="k")
        assert s.llm_provider == "openai"
        assert s.llm.provider == "openai"

    def test_nested_embedding_populated(self, monkeypatch):
        monkeypatch.setenv("ENABLE_VISUAL_EMBEDDINGS", "false")
        monkeypatch.setenv("EMBEDDING_PROVIDER", "openai")
        monkeypatch.setenv("EMBEDDING_DIMENSIONS", "1024")
        monkeypatch.setenv("EMBEDDING_BATCH_SIZE", "32")
        s = Settings(anthropic_api_key="k", openai_api_key="k")
        assert s.embedding is not None
        assert s.embedding.provider == "openai"
        assert s.embedding.model == "text-embedding-3-large"
        assert s.embedding.dimensions == 1024
        assert s.embedding.batch_size == 32
        assert s.embedding.enable_visual is False

    def test_nested_retrieval_populated(self, monkeypatch):
        monkeypatch.setenv("ENABLE_RERANKER", "false")
        s = Settings(anthropic_api_key="k", openai_api_key="k")
        assert s.retrieval is not None
        assert s.retrieval.text_limit == 40
        assert s.retrieval.graph_limit == 20
        assert s.retrieval.enable_reranker is False
        assert s.retrieval.entity_threshold == 0.5

    def test_nested_auth_populated(self):
        s = Settings(anthropic_api_key="k", openai_api_key="k")
        assert s.auth is not None
        assert s.auth.jwt_algorithm == "HS256"
        assert s.auth.jwt_access_token_expire_minutes == 30
        assert s.auth.require_matter_header is True

    def test_nested_processing_populated(self, monkeypatch):
        monkeypatch.setenv("ENABLE_RELATIONSHIP_EXTRACTION", "false")
        s = Settings(anthropic_api_key="k", openai_api_key="k")
        assert s.processing is not None
        assert s.processing.chunk_size == 512
        assert s.processing.chunk_overlap == 64
        assert s.processing.celery_concurrency == 1
        assert s.processing.enable_relationship_extraction is False
