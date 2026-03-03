"""Tests for M17 local deployment infrastructure."""

import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.config import Settings

# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------


class TestLocalDeploymentConfig:
    """Verify Settings accepts local-only provider configuration."""

    def test_config_loading_with_local_providers(self):
        """Settings with vllm + local embedding succeeds and nested groups reflect values."""
        s = Settings(
            llm_provider="vllm",
            vllm_base_url="http://localhost:8080/v1",
            llm_model="Qwen/Qwen3-235B-A22B",
            embedding_provider="local",
            local_embedding_model="BAAI/bge-m3",
            enable_reranker=True,
            anthropic_api_key="",
            openai_api_key="",
        )

        assert s.llm is not None
        assert s.llm.provider == "vllm"
        assert s.llm.vllm_base_url == "http://localhost:8080/v1"
        assert s.llm.model == "Qwen/Qwen3-235B-A22B"

        assert s.embedding is not None
        assert s.embedding.provider == "local"
        assert s.embedding.local_model == "BAAI/bge-m3"

        assert s.retrieval is not None
        assert s.retrieval.enable_reranker is True

    def test_vllm_client_factory_uses_correct_base_url(self):
        """LLMClient with vllm provider creates an OpenAI client with the correct base_url."""
        from app.common.llm import LLMClient

        s = Settings(
            llm_provider="vllm",
            vllm_base_url="http://localhost:8080/v1",
            llm_model="Qwen/Qwen3-235B-A22B",
            anthropic_api_key="",
            openai_api_key="",
        )

        client = LLMClient(s)
        assert client.provider == "vllm"
        assert client.model == "Qwen/Qwen3-235B-A22B"
        # The underlying OpenAI client should have the vLLM base_url
        assert str(client._client.base_url).rstrip("/").endswith("/v1")

    def test_config_loading_with_ollama_provider(self):
        s = Settings(
            llm_provider="ollama",
            ollama_base_url="http://localhost:11434/v1",
            llm_model="llama3.1:70b",
            anthropic_api_key="",
            openai_api_key="",
        )
        assert s.llm.provider == "ollama"
        assert s.llm.ollama_base_url == "http://localhost:11434/v1"
        assert s.llm.model == "llama3.1:70b"

    def test_ollama_client_factory_uses_correct_base_url(self):
        from app.common.llm import LLMClient

        s = Settings(
            llm_provider="ollama",
            ollama_base_url="http://localhost:11434/v1",
            llm_model="llama3.1:70b",
            anthropic_api_key="",
            openai_api_key="",
        )
        client = LLMClient(s)
        assert client.provider == "ollama"
        assert "11434" in str(client._client.base_url)

    def test_docker_compose_local_config_valid(self, tmp_path: Path):
        """docker compose -f docker-compose.yml -f docker-compose.local.yml config validates."""
        # Create a minimal .env.local so docker compose doesn't error on missing env_file
        project_root = Path(__file__).resolve().parents[2]
        env_local = project_root / ".env.local"
        created = not env_local.exists()
        if created:
            env_local.write_text("# temp for test\nPOSTGRES_PASSWORD=test\n")
        try:
            result = subprocess.run(
                [
                    "docker",
                    "compose",
                    "-f",
                    "docker-compose.yml",
                    "-f",
                    "docker-compose.local.yml",
                    "config",
                    "--quiet",
                ],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(project_root),
            )
            assert result.returncode == 0, f"docker compose config failed: {result.stderr}"
        finally:
            if created:
                env_local.unlink(missing_ok=True)

    def test_config_loading_with_ollama_embedding_provider(self):
        """Settings with ollama embedding provider populates nested config correctly."""
        s = Settings(
            llm_provider="anthropic",
            embedding_provider="ollama",
            ollama_base_url="http://localhost:11434/v1",
            ollama_embedding_model="nomic-embed-text",
            embedding_dimensions=768,
            anthropic_api_key="test-key",
            openai_api_key="",
        )

        assert s.embedding is not None
        assert s.embedding.provider == "ollama"
        assert s.embedding.ollama_model == "nomic-embed-text"
        # /v1 suffix should be stripped for the native embedding API
        assert s.embedding.ollama_base_url == "http://localhost:11434"

    def test_config_loading_with_tei_providers(self):
        """Settings accepts tei embedding provider and TEI URLs in nested config groups."""
        s = Settings(
            llm_provider="vllm",
            vllm_base_url="http://localhost:8080/v1",
            llm_model="Qwen/Qwen3-235B-A22B",
            embedding_provider="tei",
            tei_embedding_url="http://tei-embedder:80",
            enable_reranker=True,
            reranker_provider="tei",
            tei_reranker_url="http://tei-reranker:80",
            anthropic_api_key="",
            openai_api_key="",
        )

        assert s.embedding is not None
        assert s.embedding.provider == "tei"
        assert s.embedding.tei_url == "http://tei-embedder:80"

        assert s.retrieval is not None
        assert s.retrieval.reranker_provider == "tei"
        assert s.retrieval.tei_reranker_url == "http://tei-reranker:80"


# ---------------------------------------------------------------------------
# TEI Embedding Provider tests
# ---------------------------------------------------------------------------


class TestTEIEmbeddingProvider:
    """Verify TEIEmbeddingProvider calls TEI /embed endpoint correctly."""

    @pytest.mark.asyncio
    async def test_tei_embedding_provider_embed_query(self):
        """Single query embedding calls TEI /embed and returns vector."""
        from app.common.embedder import TEIEmbeddingProvider

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [[0.1, 0.2, 0.3, 0.4]]
        mock_response.raise_for_status = MagicMock()

        provider = TEIEmbeddingProvider(base_url="http://tei:80", dimensions=4)
        provider._client = AsyncMock(spec=httpx.AsyncClient)
        provider._client.post = AsyncMock(return_value=mock_response)

        result = await provider.embed_query("test query")

        provider._client.post.assert_called_once_with(
            "/embed",
            json={"inputs": ["test query"], "truncate": True},
        )
        assert result == [0.1, 0.2, 0.3, 0.4]

    @pytest.mark.asyncio
    async def test_tei_embedding_provider_embed_texts(self):
        """Multiple texts are sent in a single /embed call."""
        from app.common.embedder import TEIEmbeddingProvider

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            [0.1, 0.2, 0.3],
            [0.4, 0.5, 0.6],
        ]
        mock_response.raise_for_status = MagicMock()

        provider = TEIEmbeddingProvider(base_url="http://tei:80", dimensions=3)
        provider._client = AsyncMock(spec=httpx.AsyncClient)
        provider._client.post = AsyncMock(return_value=mock_response)

        result = await provider.embed_texts(["chunk 1", "chunk 2"])

        assert len(result) == 2
        assert result[0] == [0.1, 0.2, 0.3]
        assert result[1] == [0.4, 0.5, 0.6]

    @pytest.mark.asyncio
    async def test_tei_embedding_provider_truncates_dimensions(self):
        """Vectors are truncated to configured dimensions."""
        from app.common.embedder import TEIEmbeddingProvider

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [[0.1, 0.2, 0.3, 0.4, 0.5]]
        mock_response.raise_for_status = MagicMock()

        provider = TEIEmbeddingProvider(base_url="http://tei:80", dimensions=3)
        provider._client = AsyncMock(spec=httpx.AsyncClient)
        provider._client.post = AsyncMock(return_value=mock_response)

        result = await provider.embed_texts(["text"])

        assert len(result[0]) == 3
        assert result[0] == [0.1, 0.2, 0.3]

    @pytest.mark.asyncio
    async def test_tei_embedding_provider_empty_raises(self):
        """Empty text list raises ValueError."""
        from app.common.embedder import TEIEmbeddingProvider

        provider = TEIEmbeddingProvider(base_url="http://tei:80", dimensions=3)

        with pytest.raises(ValueError, match="empty"):
            await provider.embed_texts([])

    def test_tei_embedding_provider_satisfies_protocol(self):
        """TEIEmbeddingProvider is a valid EmbeddingProvider."""
        from app.common.embedder import EmbeddingProvider, TEIEmbeddingProvider

        provider = TEIEmbeddingProvider(base_url="http://tei:80", dimensions=3)
        assert isinstance(provider, EmbeddingProvider)


# ---------------------------------------------------------------------------
# TEI Reranker tests
# ---------------------------------------------------------------------------


class TestTEIReranker:
    """Verify TEIReranker calls TEI /rerank endpoint correctly."""

    @pytest.mark.asyncio
    async def test_tei_reranker_rerank(self):
        """Rerank returns results sorted by TEI score, maps back to original dicts."""
        from app.query.reranker import TEIReranker

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"index": 0, "score": 0.3},
            {"index": 1, "score": 0.9},
            {"index": 2, "score": 0.6},
        ]
        mock_response.raise_for_status = MagicMock()

        reranker = TEIReranker(base_url="http://tei:80")
        reranker._client = AsyncMock(spec=httpx.AsyncClient)
        reranker._client.post = AsyncMock(return_value=mock_response)

        results = [
            {"chunk_text": "first", "id": "a"},
            {"chunk_text": "second", "id": "b"},
            {"chunk_text": "third", "id": "c"},
        ]

        ranked = await reranker.rerank("query", results, top_n=3)

        reranker._client.post.assert_called_once_with(
            "/rerank",
            json={"query": "query", "texts": ["first", "second", "third"], "truncate": True},
        )
        # Should be sorted descending by score
        assert ranked[0]["id"] == "b"
        assert ranked[0]["score"] == 0.9
        assert ranked[1]["id"] == "c"
        assert ranked[2]["id"] == "a"

    @pytest.mark.asyncio
    async def test_tei_reranker_handles_empty(self):
        """Empty input returns empty list without calling TEI."""
        from app.query.reranker import TEIReranker

        reranker = TEIReranker(base_url="http://tei:80")
        reranker._client = AsyncMock(spec=httpx.AsyncClient)

        result = await reranker.rerank("query", [])

        assert result == []
        reranker._client.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_tei_reranker_respects_top_n(self):
        """Only top_n results are returned."""
        from app.query.reranker import TEIReranker

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"index": 0, "score": 0.3},
            {"index": 1, "score": 0.9},
            {"index": 2, "score": 0.6},
        ]
        mock_response.raise_for_status = MagicMock()

        reranker = TEIReranker(base_url="http://tei:80")
        reranker._client = AsyncMock(spec=httpx.AsyncClient)
        reranker._client.post = AsyncMock(return_value=mock_response)

        results = [
            {"chunk_text": "first", "id": "a"},
            {"chunk_text": "second", "id": "b"},
            {"chunk_text": "third", "id": "c"},
        ]

        ranked = await reranker.rerank("query", results, top_n=2)

        assert len(ranked) == 2
        assert ranked[0]["score"] == 0.9
        assert ranked[1]["score"] == 0.6


# ---------------------------------------------------------------------------
# DI Factory tests
# ---------------------------------------------------------------------------


class TestDIFactory:
    """Verify DI factory functions select correct providers."""

    def test_factory_selects_tei_embedding_provider(self):
        """get_embedder returns TEIEmbeddingProvider when EMBEDDING_PROVIDER=tei."""
        from app.common.embedder import TEIEmbeddingProvider

        mock_settings = MagicMock()
        mock_settings.embedding_provider = "tei"
        mock_settings.tei_embedding_url = "http://tei:80"
        mock_settings.embedding_dimensions = 1024

        with patch("app.dependencies.get_settings", return_value=mock_settings):
            from app.dependencies import get_embedder

            get_embedder.cache_clear()
            embedder = get_embedder()
            assert isinstance(embedder, TEIEmbeddingProvider)
            get_embedder.cache_clear()

    def test_factory_selects_ollama_embedding_provider(self):
        """get_embedder returns OllamaEmbeddingProvider when EMBEDDING_PROVIDER=ollama."""
        from app.common.embedder import OllamaEmbeddingProvider

        mock_settings = MagicMock()
        mock_settings.embedding_provider = "ollama"
        mock_settings.ollama_base_url = "http://localhost:11434/v1"
        mock_settings.ollama_embedding_model = "nomic-embed-text"
        mock_settings.embedding_dimensions = 768

        with patch("app.dependencies.get_settings", return_value=mock_settings):
            from app.dependencies import get_embedder

            get_embedder.cache_clear()
            embedder = get_embedder()
            assert isinstance(embedder, OllamaEmbeddingProvider)
            get_embedder.cache_clear()

    def test_factory_selects_tei_reranker(self):
        """get_reranker returns TEIReranker when RERANKER_PROVIDER=tei."""
        from app.query.reranker import TEIReranker

        mock_settings = MagicMock()
        mock_settings.enable_reranker = True
        mock_settings.reranker_provider = "tei"
        mock_settings.tei_reranker_url = "http://tei:80"

        with patch("app.dependencies.get_settings", return_value=mock_settings):
            from app.dependencies import get_reranker

            get_reranker.cache_clear()
            reranker = get_reranker()
            assert isinstance(reranker, TEIReranker)
            get_reranker.cache_clear()
