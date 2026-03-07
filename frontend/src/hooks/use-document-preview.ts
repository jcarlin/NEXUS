import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/api/client";

// Simple local type — the endpoint returns a presigned URL but its shape
// doesn't match the generated DocumentPreview schema.
interface PreviewResponse {
  preview_url: string;
}

export function useDocumentPreview(docId: string | null, page?: number | null) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["document-preview", docId, page],
    queryFn: () =>
      apiClient<PreviewResponse>({
        url: `/api/v1/documents/${docId}/preview`,
        method: "GET",
        params: { page: page ?? 1 },
      }),
    enabled: !!docId,
    staleTime: 5 * 60 * 1000,
  });

  return {
    previewUrl: data?.preview_url ?? null,
    isLoading,
    error: error as Error | null,
  };
}
