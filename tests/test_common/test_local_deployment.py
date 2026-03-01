"""Tests for M17 local deployment infrastructure."""

import subprocess
from pathlib import Path

from app.config import Settings


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
