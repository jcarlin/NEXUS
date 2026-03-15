# Plan: Add Ollama Embedding Service to GCP VM

**Status:** Planned (not yet implemented)
**Date:** 2026-03-14

## Context

The GCP VM (`e2-standard-4`, 4 vCPU / 16GB) currently uses OpenAI `text-embedding-3-large` for embeddings via API. The `OllamaEmbeddingProvider` already exists in the codebase (`app/common/embedder.py:389-453`) and the DI factory (`app/dependencies.py:217-222`) wires it up automatically — it just needs an Ollama server to talk to.

**Why:** Eliminates OpenAI API dependency for embeddings, reduces cost, keeps document content on-machine (better for privileged legal docs). CPU inference for `nomic-embed-text` is practical on the VM — same as local dev.

## Changes

### 1. Add `ollama` service to `docker-compose.cloud.yml`

```yaml
ollama:
  image: ollama/ollama:latest
  volumes:
    - ollama_models:/root/.ollama
  environment:
    OLLAMA_HOST: 0.0.0.0:11434
  healthcheck:
    test: ["CMD-SHELL", "curl -sf http://localhost:11434/api/tags || exit 1"]
    interval: 15s
    timeout: 10s
    retries: 5
    start_period: 30s
  restart: unless-stopped
  logging: *default-logging
  deploy:
    resources:
      limits:
        memory: 2G
```

- No host port binding (internal Docker network only, consistent with other cloud services)
- Volume `ollama_models` persists downloaded models across restarts
- Memory capped at 2G (plenty for `nomic-embed-text` at ~500MB loaded)

### 2. Add env override + dependency for `api` and `worker` in cloud overlay

```yaml
api:
  environment:
    OLLAMA_BASE_URL: http://ollama:11434
  depends_on:
    ollama:
      condition: service_healthy

worker:
  environment:
    OLLAMA_BASE_URL: http://ollama:11434
  depends_on:
    ollama:
      condition: service_healthy
```

### 3. Add `ollama_models` volume declaration

### 4. Update `docs/CLOUD-DEPLOY.md` — add Ollama section

One-time model pull after first deploy:
```bash
docker exec -it nexus-ollama-1 ollama pull nomic-embed-text
```

Note: The embedding provider switch (`EMBEDDING_PROVIDER=ollama`) will be done manually via the admin UI at runtime — do NOT change `.env` or env vars in compose for this. The compose changes only make the Ollama server available on the Docker network.

### 5. Update `.env.example` — document Ollama embedding config

## Files to modify

| File | Change |
|------|--------|
| `docker-compose.cloud.yml` | Add `ollama` service, volume, env overrides for api/worker |
| `docs/CLOUD-DEPLOY.md` | Add Ollama setup section (model pull, provider switch via UI) |
| `.env.example` | Add/update Ollama embedding comments |

## No code changes needed

`OllamaEmbeddingProvider` and its DI factory already work.

## Verification

1. `docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.cloud.yml config` — validate merged config
2. On GCP after deploy: pull model, update `.env`, restart api/worker, hit `/api/v1/health`, run a query
3. `pytest tests/test_common/test_embedder.py -v`

## Important: Re-ingestion required

Switching embedding providers changes the vector space. Existing Qdrant vectors (OpenAI `text-embedding-3-large`, 3072d) are incompatible with `nomic-embed-text` (768d). A wipe + re-ingest is required after switching. See `memory/wipe-reingest.md` for the procedure.
