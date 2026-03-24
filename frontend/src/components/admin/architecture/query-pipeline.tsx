import { PipelineNode, Arrow } from "./pipeline-node";
import { ToolGrid } from "./tool-grid";
import { FlagBadge } from "./flag-badge";

interface QueryPipelineProps {
  flagMap: Map<string, boolean>;
  queryModel: string | null;
  embeddingInfo: { provider: string; model: string; dimensions: number } | null;
  settings: Map<string, string | number>;
  onToggleFlag?: (flagName: string, newValue: boolean) => void;
}

export function QueryPipeline({ flagMap, queryModel, embeddingInfo, onToggleFlag }: QueryPipelineProps) {
  const flag = (name: string) => flagMap.get(name) ?? false;
  const fb = (name: string, label?: string) => ({
    name, enabled: flag(name), label, onToggle: onToggleFlag,
  });

  return (
    <div className="mx-auto flex max-w-3xl flex-col items-center">
      {/* Entry */}
      <div className="inline-flex items-center gap-2 rounded-full border border-blue-500/40 bg-blue-500/5 px-5 py-2.5 text-sm font-semibold text-blue-600 dark:text-blue-400">
        <span className="h-2 w-2 animate-pulse rounded-full bg-blue-500" />
        USER QUERY &rarr; POST /query/stream (SSE)
      </div>
      <Arrow />

      {/* Router */}
      <PipelineNode title="Query Router">
        Privilege enforcement: role &rarr; <code className="rounded bg-muted px-1 text-[11px]">exclude_privilege_statuses</code>
        <br />
        Dataset scoping &bull; Chat history via PostgresCheckpointer
        <br />
        <span className="inline-flex items-center gap-1.5">
          Graph: Agentic pipeline
          <FlagBadge {...fb("enable_agentic_pipeline")} />
          <FlagBadge {...fb("enable_auto_graph_routing", "AUTO ROUTE")} />
        </span>
      </PipelineNode>
      <Arrow />

      {/* case_context_resolve */}
      <PipelineNode title="case_context_resolve">
        <span className="inline-flex flex-wrap items-center gap-1.5">
          Load claims, parties, terms, timeline
          <FlagBadge {...fb("enable_case_setup_agent", "CASE CTX")} />
        </span>
        <br />
        <span className="inline-flex flex-wrap items-center gap-1.5">
          Prompt routing: factual | analytical | exploratory | timeline
          <FlagBadge {...fb("enable_prompt_routing", "ROUTING")} />
        </span>
        <br />
        <span className="inline-flex flex-wrap items-center gap-1.5">
          Adaptive retrieval depth by query type
          <FlagBadge {...fb("enable_adaptive_retrieval_depth", "ADAPTIVE")} />
        </span>
      </PipelineNode>
      <Arrow />

      {/* investigation_agent */}
      <PipelineNode title="investigation_agent" variant="primary">
        <span className="text-xs text-muted-foreground">
          LangGraph <code className="rounded bg-muted px-1 text-[11px]">create_react_agent</code>
          {queryModel && (
            <> &mdash; LLM: <code className="rounded bg-muted px-1 text-[11px]">{queryModel}</code></>
          )}
        </span>
        <br />
        Iterative tool loop &bull; System prompt = base + query-type addendum + case context
        <br />
        <span className="inline-flex flex-wrap items-center gap-1.5">
          Max 30 steps &bull; Tool budget: ~5 per investigation
          <FlagBadge {...fb("enable_ai_audit_logging", "AI AUDIT")} />
        </span>
        <ToolGrid flagMap={flagMap} />
      </PipelineNode>
      <Arrow />

      {/* post_agent_extract */}
      <PipelineNode
        title="post_agent_extract"
        flags={[fb("enable_hallugraph_alignment", "HALLUGRAPH")]}
      >
        Extract response, source documents, entities, atomic claims
        <br />
        Validate mentioned entities against Neo4j knowledge graph
      </PipelineNode>
      <Arrow />

      {/* verify_citations */}
      <PipelineNode
        title="verify_citations"
        disabled={!flag("enable_citation_verification")}
        flags={[fb("enable_citation_verification", "VERIFY")]}
      >
        Chain-of-Verification: decompose &rarr; re-retrieve &rarr; LLM judge
        <br />
        Up to 10 claims &bull; Status: verified | flagged | unverified
      </PipelineNode>
      <Arrow dim={!flag("enable_self_reflection")} />

      {/* reflect */}
      <PipelineNode
        title="reflect"
        disabled={!flag("enable_self_reflection")}
        flags={[fb("enable_self_reflection")]}
      >
        Self-reflection loop: retry when faithfulness &lt; 0.6
        <br />
        Re-inject flagged claims for re-investigation (max 1 retry)
      </PipelineNode>
      <Arrow />

      {/* generate_follow_ups */}
      <PipelineNode title="generate_follow_ups">
        LLM generates 3 follow-up questions based on query + response + entities
      </PipelineNode>
      <Arrow />

      {/* quality_monitoring (optional) */}
      <PipelineNode
        title="quality_monitoring"
        disabled={!flag("enable_production_quality_monitoring")}
        flags={[fb("enable_production_quality_monitoring", "QUALITY")]}
      >
        Fire-and-forget: sample-based scoring of retrieval relevance + faithfulness
      </PipelineNode>
      <Arrow />

      {/* Output */}
      <div className="inline-flex items-center gap-2 rounded-full border border-emerald-500/40 bg-emerald-500/5 px-5 py-2.5 text-sm font-semibold text-emerald-600 dark:text-emerald-400">
        SSE Response: sources &rarr; tokens &rarr; tool_calls &rarr; done
      </div>

      {/* Hybrid retrieval detail */}
      <div className="mt-10 w-full">
        <h3 className="mb-1 text-sm font-semibold">Hybrid Retrieval Detail</h3>
        <p className="mb-3 text-xs text-muted-foreground">
          Used internally by vector_search, temporal_search, and citation verification
        </p>
        <PipelineNode title="Retrieval Pipeline" className="max-w-none">
          <span className="font-medium text-foreground">Dense:</span>{" "}
          {embeddingInfo ? (
            <>
              {embeddingInfo.provider} <code className="rounded bg-muted px-1 text-[11px]">{embeddingInfo.model}</code> ({embeddingInfo.dimensions}d)
            </>
          ) : "loading..."}
          <span className="ml-2 inline-flex gap-1">
            <FlagBadge {...fb("enable_hyde", "HyDE")} />
            <FlagBadge {...fb("enable_multi_query_expansion", "MULTI-Q")} />
          </span>
          <br />
          <span className="font-medium text-foreground">Sparse:</span>{" "}
          FastEmbed BM42
          <FlagBadge {...fb("enable_sparse_embeddings")} />
          <br />
          <span className="font-medium text-foreground">Fusion:</span>{" "}
          Qdrant native RRF (prefetch dense + sparse &rarr; FusionQuery)
          <br /><br />
          <span className="font-medium text-foreground">Post-retrieval:</span>
          <br />
          &bull; Near-duplicate dedup <FlagBadge {...fb("enable_near_duplicate_detection", "DEDUP")} />
          <br />
          &bull; Cross-encoder rerank (BGE v2-m3) <FlagBadge {...fb("enable_reranker", "RERANK")} />
          <br />
          &bull; Visual rerank blend: 70% text + 30% ColQwen2.5 <FlagBadge {...fb("enable_visual_embeddings", "VISUAL")} />
          <br />
          <span className="inline-flex gap-1 pt-1">
            <FlagBadge {...fb("enable_retrieval_grading", "CRAG")} />
            <FlagBadge {...fb("enable_multi_representation", "MULTI-REPR")} />
          </span>
        </PipelineNode>
      </div>

      {/* Data stores */}
      <div className="mt-10 w-full">
        <h3 className="mb-3 text-sm font-semibold">Data Stores</h3>
        <div className="grid grid-cols-3 gap-3">
          <PipelineNode title="Qdrant" variant="store">
            nexus_text: dense + sparse RRF
            <br />
            nexus_visual: ColQwen2.5 MaxSim
          </PipelineNode>
          <PipelineNode title="Neo4j" variant="store">
            :Entity, :Document, :Chunk, :Claim
            <br />
            MENTIONED_IN, RELATED_TO, REPORTS_TO
          </PipelineNode>
          <PipelineNode title="PostgreSQL" variant="store">
            chat_messages, case_contexts
            <br />
            audit_log, ai_audit_log, documents
          </PipelineNode>
        </div>
      </div>
    </div>
  );
}
