import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/api/client";

// Simple local type — the backend returns a presigned URL object but it's not
// modeled as a named schema in the OpenAPI spec.
interface DownloadResponse {
  download_url: string;
}

export function useDocumentDownload(docId: string | null) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["document-download", docId],
    queryFn: () =>
      apiClient<DownloadResponse>({
        url: `/api/v1/documents/${docId}/download`,
        method: "GET",
      }),
    enabled: !!docId,
    staleTime: 5 * 60 * 1000,
  });

  return {
    downloadUrl: data?.download_url ?? null,
    isLoading,
    error: error as Error | null,
  };
}
