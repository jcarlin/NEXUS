# Local LLM Feasibility Analysis (GPU VM, T4 16GB)

## Summary

No model in ~12GB VRAM matches Gemini 2.0 Flash for complex legal reasoning. However, for structured extraction tasks (entity extraction, relationship extraction, JSON output, summarization), the gap narrows to 85-95% of Flash quality.

**Recommended: Hybrid architecture** — local model for high-volume ingestion tiers, Gemini for quality-critical query tier. Zero code changes needed (tier system handles routing).

## Tier Assignment

| Tier | Model | Rationale |
|---|---|---|
| **query** | Gemini 2.0 Flash (keep) | Agentic reasoning, citations, reflection — quality matters most |
| **analysis** | Local (Qwen 14B AWQ) | Follow-ups, sentiment, case setup — structured output, high volume |
| **ingestion** | Local (Qwen 14B AWQ) | Relationship extraction, contextual chunks — highest volume, lowest quality bar |

## VRAM Budget (T4, 16GB)

| Component | VRAM |
|---|---|
| Infinity BGE-M3 embedder (fp16) | ~2.2 GB |
| Infinity BGE-reranker (fp16) | ~1.1 GB |
| vLLM Qwen 2.5 14B AWQ | ~8-10 GB |
| KV cache (8K context) | ~1-2 GB |
| **Total** | **~12.5-15.3 GB** |

Fallback: Qwen3 8B AWQ (~5-6GB) if 14B causes OOM.

## Model Candidates

| Model | VRAM (AWQ) | Context | MMLU | License |
|---|---|---|---|---|
| **Qwen 2.5 14B Instruct AWQ** | ~8-10 GB | 32K | 79.7% | Apache 2.0 |
| **Qwen3 8B AWQ** | ~5-6 GB | 32K | ~75% | Apache 2.0 |
| Phi-4-Reasoning 14B AWQ | ~8-10 GB | 16K | High | MIT |
| Gemma 2 9B | ~5-6 GB | 8K | 71.3% | Gemma license |
| Llama 3.1 8B | ~5-6 GB | 128K | 73.0% | Llama license |

T4 constraint: Must use AWQ quantization (INT4/FP8 require compute cap 8.0+).

## Activation

vLLM is in `docker-compose.gpu.yml` with `profiles: [vllm]` (opt-in):

```bash
# Start vLLM
docker compose -f ... -f docker-compose.gpu.yml --profile vllm up -d vllm

# Register provider + assign tiers via admin UI or API
POST /admin/llm-config/providers  {"label": "vLLM Local", "provider_type": "vllm", "base_url": "http://vllm:8000/v1"}
PUT /admin/llm-config/tiers/ingestion  {"provider_id": "...", "model": "Qwen/Qwen2.5-14B-Instruct-AWQ"}
PUT /admin/llm-config/tiers/analysis   {"provider_id": "...", "model": "Qwen/Qwen2.5-14B-Instruct-AWQ"}
POST /admin/llm-config/apply
```

## Risks

- **VRAM contention**: Monitor `nvidia-smi`. Reduce `--gpu-memory-utilization` or switch to 8B model if OOM.
- **Quality regression**: Test with 10 docs before bulk import. Compare relationship extraction output vs Gemini.
- **Context limit**: Default 8K. Set `VLLM_MAX_MODEL_LEN=16384` for relationship extraction (requests 16K tokens).
