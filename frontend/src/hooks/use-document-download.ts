import { useQuery } from "@tanstack/react-query";
import { apiFetchRaw } from "@/api/client";

export function useDocumentDownload(docId: string | null) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["document-download", docId],
    queryFn: async ({ signal }) => {
      const res = await apiFetchRaw(`/api/v1/documents/${docId}/download`, signal);
      const blob = await res.blob();
      const filename =
        res.headers.get("content-disposition")?.match(/filename="(.+)"/)?.[1] ?? "download";
      return { url: URL.createObjectURL(blob), filename };
    },
    enabled: !!docId,
    staleTime: 5 * 60 * 1000,
  });

  return {
    downloadUrl: data?.url ?? null,
    filename: data?.filename ?? null,
    isLoading,
    error: error as Error | null,
  };
}
