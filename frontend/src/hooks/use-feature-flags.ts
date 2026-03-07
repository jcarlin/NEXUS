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
