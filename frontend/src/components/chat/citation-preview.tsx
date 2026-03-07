import { useState, useEffect, useMemo } from "react";
import { Expand, FileText } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { Skeleton } from "@/components/ui/skeleton";
import { useDocumentPreview } from "@/hooks/use-document-preview";
import { detectDocumentType } from "@/lib/utils";
import type { SourceDocument } from "@/types";
import { apiClient } from "@/api/client";

interface CitationPreviewProps {
  source: SourceDocument;
  allSources: SourceDocument[];
  onExpandClick: () => void;
}

function TextExcerptPreview({
  source,
  onExpandClick,
}: {
  source: SourceDocument;
  onExpandClick: () => void;
}) {
  const [textContent, setTextContent] = useState<string | null>(null);
  const downloadUrl = source.download_url;

  useEffect(() => {
    if (!downloadUrl) return;
    const controller = new AbortController();
    fetch(downloadUrl, { signal: controller.signal })
      .then((res) => (res.ok ? res.text() : null))
      .then((text) => {
        if (text) setTextContent(text);
      })
      .catch(() => {});
    return () => controller.abort();
  }, [downloadUrl]);

  const highlightedExcerpt = useMemo(() => {
    if (!textContent) return null;
    const chunkText = source.chunk_text;
    const idx = textContent.toLowerCase().indexOf(chunkText.toLowerCase().slice(0, 100));
    if (idx === -1) return null;

    // Show ~500 chars window around match
    const windowStart = Math.max(0, idx - 100);
    const windowEnd = Math.min(textContent.length, idx + chunkText.length + 100);
    const before = textContent.slice(windowStart, idx);
    const match = textContent.slice(idx, idx + chunkText.length);
    const after = textContent.slice(idx + chunkText.length, windowEnd);

    return { before, match, after, hasPrefix: windowStart > 0, hasSuffix: windowEnd < textContent.length };
  }, [textContent, source.chunk_text]);

  if (highlightedExcerpt) {
    return (
      <button
        type="button"
        className="w-full cursor-pointer rounded-md border bg-muted/30 p-3 text-left transition-colors hover:bg-muted/50"
        onClick={onExpandClick}
      >
        <pre className="whitespace-pre-wrap break-words text-xs leading-relaxed">
          {highlightedExcerpt.hasPrefix && <span className="text-muted-foreground">...</span>}
          {highlightedExcerpt.before}
          <mark className="citation-highlight">{highlightedExcerpt.match}</mark>
          {highlightedExcerpt.after}
          {highlightedExcerpt.hasSuffix && <span className="text-muted-foreground">...</span>}
        </pre>
        <div className="mt-2 flex items-center gap-1 text-[10px] text-muted-foreground">
          <Expand className="h-3 w-3" />
          Click to expand
        </div>
      </button>
    );
  }

  // Fallback: plain excerpt
  return null;
}

export function CitationPreview({
  source,
  allSources,
  onExpandClick,
}: CitationPreviewProps) {
  const queryClient = useQueryClient();
  const viewType = detectDocumentType(null, source.filename);
  const isPdfOrImage = viewType === "pdf" || viewType === "image";

  const docId = source.doc_id ?? source.id;
  const { previewUrl, isLoading: previewLoading } = useDocumentPreview(
    isPdfOrImage ? docId : null,
    source.page,
  );

  // Prefetch adjacent source thumbnails
  useEffect(() => {
    if (!isPdfOrImage) return;
    const currentIdx = allSources.findIndex((s) => s.id === source.id);
    const adjacent = [currentIdx - 1, currentIdx + 1]
      .filter((i) => i >= 0 && i < allSources.length)
      .map((i) => allSources[i]!);

    for (const adj of adjacent) {
      const adjDocId = adj.doc_id ?? adj.id;
      const adjType = detectDocumentType(null, adj.filename);
      if (adjType === "pdf" || adjType === "image") {
        queryClient.prefetchQuery({
          queryKey: ["document-preview", adjDocId, adj.page],
          queryFn: () =>
            apiClient<{ preview_url: string }>({
              url: `/api/v1/documents/${adjDocId}/preview`,
              method: "GET",
              params: { page: adj.page ?? 1 },
            }),
          staleTime: 5 * 60 * 1000,
        });
      }
    }
  }, [source.id, allSources, isPdfOrImage, queryClient]);

  // PDF/Image: page thumbnail
  if (isPdfOrImage) {
    return (
      <div className="space-y-3">
        {previewLoading ? (
          <Skeleton className="aspect-[8.5/11] w-full rounded-md" />
        ) : previewUrl ? (
          <button
            type="button"
            className="group w-full cursor-pointer overflow-hidden rounded-md border bg-muted/30 transition-colors hover:bg-muted/50"
            onClick={onExpandClick}
          >
            <div className="relative">
              <img
                src={previewUrl}
                alt={`Page ${source.page ?? 1} of ${source.filename}`}
                className="w-full object-contain"
              />
              <div className="absolute inset-0 flex items-center justify-center bg-black/0 transition-colors group-hover:bg-black/20">
                <Expand className="h-6 w-6 text-white opacity-0 transition-opacity group-hover:opacity-100" />
              </div>
            </div>
          </button>
        ) : (
          <div className="flex aspect-[8.5/11] w-full items-center justify-center rounded-md border bg-muted/30">
            <FileText className="h-12 w-12 text-muted-foreground/30" />
          </div>
        )}

        {/* Excerpt with accent bar */}
        <div className="border-l-2 border-amber-500/60 pl-3">
          <p className="mb-1 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
            Excerpt
          </p>
          <p className="text-xs leading-relaxed text-foreground/80">
            {source.chunk_text}
          </p>
        </div>
      </div>
    );
  }

  // Text/Email: try highlighted excerpt, fallback to plain
  if (viewType === "text" || viewType === "email") {
    return (
      <div className="space-y-3">
        <TextExcerptPreview source={source} onExpandClick={onExpandClick} />
        <div className="border-l-2 border-amber-500/60 pl-3">
          <p className="mb-1 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
            Excerpt
          </p>
          <p className="text-xs leading-relaxed text-foreground/80">
            {source.chunk_text}
          </p>
        </div>
      </div>
    );
  }

  // Unknown: plain excerpt only
  return (
    <div>
      <p className="mb-1 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
        Excerpt
      </p>
      <p className="rounded-md bg-muted/50 p-3 text-xs leading-relaxed text-foreground/80">
        {source.chunk_text}
      </p>
    </div>
  );
}
