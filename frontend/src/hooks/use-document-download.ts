import { useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiFetchRaw } from "@/api/client";

export function useDocumentDownload(docId: string | null, filename?: string | null) {
  const blobUrlRef = useRef<string | null>(null);

  const { data, isLoading, error } = useQuery({
    queryKey: ["document-download", docId, filename],
    queryFn: async ({ signal }) => {
      let url = `/api/v1/documents/${docId}/download`;
      if (filename) {
        url += `?filename=${encodeURIComponent(filename)}`;
      }
      const res = await apiFetchRaw(url, signal);
      const blob = await res.blob();
      const resolvedFilename =
        res.headers.get("content-disposition")?.match(/filename="(.+)"/)?.[1] ?? "download";
      return { url: URL.createObjectURL(blob), filename: resolvedFilename };
    },
    enabled: !!docId,
    staleTime: 5 * 60 * 1000,
  });

  // Revoke previous blob URL when a new one is created or on unmount
  useEffect(() => {
    const currentUrl = data?.url ?? null;
    if (blobUrlRef.current && blobUrlRef.current !== currentUrl) {
      URL.revokeObjectURL(blobUrlRef.current);
    }
    blobUrlRef.current = currentUrl;
    return () => {
      if (blobUrlRef.current) {
        URL.revokeObjectURL(blobUrlRef.current);
        blobUrlRef.current = null;
      }
    };
  }, [data?.url]);

  return {
    downloadUrl: data?.url ?? null,
    filename: data?.filename ?? null,
    isLoading,
    error: error as Error | null,
  };
}
