import { useQuery } from "@tanstack/react-query";
import { apiFetchRaw } from "@/api/client";

export function useDocumentPreview(docId: string | null, page?: number | null) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["document-preview", docId, page],
    queryFn: async ({ signal }) => {
      const p = page ?? 1;
      const res = await apiFetchRaw(`/api/v1/documents/${docId}/preview?page=${p}`, signal);
      const blob = await res.blob();
      return URL.createObjectURL(blob);
    },
    enabled: !!docId,
    staleTime: 5 * 60 * 1000,
  });

  return { previewUrl: data ?? null, isLoading, error: error as Error | null };
}
