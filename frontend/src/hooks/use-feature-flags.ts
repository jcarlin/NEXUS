import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/api/client";

export interface FeatureFlags {
  hot_doc_detection: boolean;
  case_setup_agent: boolean;
  topic_clustering: boolean;
  graph_centrality: boolean;
  sparse_embeddings: boolean;
  near_duplicate_detection: boolean;
  reranker: boolean;
  redaction: boolean;
  visual_embeddings: boolean;
  relationship_extraction: boolean;
  email_threading: boolean;
  ai_audit_logging: boolean;
  coreference_resolution: boolean;
  batch_embeddings: boolean;
  agentic_pipeline: boolean;
  citation_verification: boolean;
  google_drive: boolean;
  prometheus_metrics: boolean;
  sso: boolean;
  memo_drafting: boolean;
  chunk_quality_scoring: boolean;
  contextual_chunks: boolean;
  retrieval_grading: boolean;
  multi_query_expansion: boolean;
  text_to_cypher: boolean;
  prompt_routing: boolean;
  question_decomposition: boolean;
  page_chat: boolean;
  page_documents: boolean;
  page_ingest: boolean;
  page_datasets: boolean;
  page_entities: boolean;
  page_comms_matrix: boolean;
  page_timeline: boolean;
  page_network_graph: boolean;
  page_hot_docs: boolean;
  page_result_set: boolean;
  page_exports: boolean;
  page_case_setup: boolean;
}

export function useFeatureFlags() {
  return useQuery({
    queryKey: ["feature-flags"],
    queryFn: () =>
      apiClient<FeatureFlags>({
        url: "/api/v1/config/features",
        method: "GET",
      }),
    staleTime: 5 * 60 * 1000,
  });
}

export function useFeatureFlag(name: keyof FeatureFlags): boolean {
  const { data } = useFeatureFlags();
  return data?.[name] ?? false;
}
