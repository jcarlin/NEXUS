import { useEffect, useCallback } from "react";
import {
  X,
  FileText,
  ExternalLink,
  Expand,
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { Link } from "@tanstack/react-router";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { CitationPreview } from "./citation-preview";
import { DocumentViewer } from "@/components/documents/document-viewer";
import { useDocumentDownload } from "@/hooks/use-document-download";
import { useCitationStore } from "@/stores/citation-store";

function CompactView() {
  const { activeSource, allSources, close, setActiveSource, expandView } =
    useCitationStore();

  return (
    <div className="flex h-full flex-col" data-testid="citation-sidebar">
      {/* Header */}
      <div className="flex items-center justify-between border-b px-3 py-3">
        <div className="flex items-center gap-2">
          <FileText className="h-4 w-4 text-muted-foreground" />
          <span className="text-sm font-semibold">
            Sources ({allSources.length})
          </span>
        </div>
        <Button variant="ghost" size="sm" className="h-7 w-7 p-0" onClick={close}>
          <X className="h-4 w-4" />
        </Button>
      </div>

      {allSources.length === 0 ? (
        <div className="flex flex-1 flex-col items-center justify-center p-6 text-center">
          <FileText className="mb-3 h-8 w-8 text-muted-foreground/50" />
          <p className="text-sm font-medium text-muted-foreground">No sources found</p>
          <p className="mt-1 text-xs text-muted-foreground/70">
            Sources will appear here when the assistant cites documents in its response.
          </p>
        </div>
      ) : (
        <>
          {/* Source tabs */}
          <div className="flex flex-wrap gap-1.5 border-b px-3 py-2">
            {allSources.map((src, idx) => (
              <button
                key={src.id}
                type="button"
                onClick={() => setActiveSource(src)}
                className={`flex h-6 min-w-6 items-center justify-center rounded-md px-1.5 text-xs font-semibold transition-colors ${
                  activeSource?.id === src.id
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted text-muted-foreground hover:bg-accent"
                }`}
              >
                {idx + 1}
              </button>
            ))}
          </div>

          {/* Active source content */}
          <ScrollArea className="flex-1">
            {activeSource && (
              <div className="space-y-4 p-4">
                {/* Filename + metadata */}
                <div>
                  <h3 className="text-sm font-medium leading-tight">
                    {activeSource.filename}
                  </h3>
                  <div className="mt-1.5 flex flex-wrap items-center gap-2">
                    {activeSource.page != null && (
                      <Badge variant="secondary" className="text-[10px]">
                        Page {activeSource.page}
                      </Badge>
                    )}
                    <Badge variant="secondary" className="text-[10px]">
                      {(activeSource.relevance_score * 100).toFixed(0)}% relevant
                    </Badge>
                  </div>
                </div>

                {/* Citation Preview (thumbnail or highlighted excerpt) */}
                <CitationPreview
                  source={activeSource}
                  allSources={allSources}
                  onExpandClick={expandView}
                />

                {/* Actions */}
                <div className="flex flex-col gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    className="justify-start gap-2 text-xs"
                    onClick={expandView}
                  >
                    <Expand className="h-3.5 w-3.5" />
                    Expand View
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    className="justify-start gap-2 text-xs"
                    asChild
                  >
                    <Link to="/documents" search={{ id: activeSource.doc_id ?? activeSource.id }}>
                      <ExternalLink className="h-3.5 w-3.5" />
                      Full Document
                    </Link>
                  </Button>
                </div>
              </div>
            )}
          </ScrollArea>
        </>
      )}
    </div>
  );
}

function ExpandedView() {
  const { activeSource, allSources, close, setActiveSource, collapseView } =
    useCitationStore();

  // Prefer the download_url already on the source (from SSE);
  // only fetch via hook when missing
  const docId = activeSource?.doc_id ?? activeSource?.id ?? null;
  const needsFetch = !activeSource?.download_url;
  const { downloadUrl: fetchedUrl, isLoading: fetchLoading } = useDocumentDownload(
    needsFetch ? docId : null,
    activeSource?.filename,
  );
  const downloadUrl = activeSource?.download_url ?? fetchedUrl;
  const downloadLoading = needsFetch && fetchLoading;

  const currentIdx = allSources.findIndex((s) => s.id === activeSource?.id);
  const hasPrev = currentIdx > 0;
  const hasNext = currentIdx < allSources.length - 1;

  const goToPrev = useCallback(() => {
    if (hasPrev) setActiveSource(allSources[currentIdx - 1]!);
  }, [hasPrev, currentIdx, allSources, setActiveSource]);

  const goToNext = useCallback(() => {
    if (hasNext) setActiveSource(allSources[currentIdx + 1]!);
  }, [hasNext, currentIdx, allSources, setActiveSource]);

  // Keyboard shortcuts: Escape to collapse, Left/Right for prev/next
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.preventDefault();
        collapseView();
      } else if (e.key === "ArrowLeft" && hasPrev) {
        e.preventDefault();
        goToPrev();
      } else if (e.key === "ArrowRight" && hasNext) {
        e.preventDefault();
        goToNext();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [collapseView, hasPrev, hasNext, goToPrev, goToNext]);

  if (!activeSource) return null;

  return (
    <div
      className="flex h-full flex-col animate-in fade-in duration-200"
      data-testid="citation-sidebar"
      data-mode="expanded"
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b px-3 py-2">
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            className="h-7 gap-1.5 px-2 text-xs"
            onClick={collapseView}
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            Back
          </Button>
          <span className="truncate text-sm font-medium">
            {activeSource.filename}
          </span>
        </div>
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="sm"
            className="h-7 w-7 p-0"
            onClick={goToPrev}
            disabled={!hasPrev}
            title="Previous source"
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="h-7 w-7 p-0"
            onClick={goToNext}
            disabled={!hasNext}
            title="Next source"
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="sm" className="h-7 w-7 p-0" onClick={close}>
            <X className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* Full document viewer */}
      <div className="min-h-0 flex-1 overflow-auto p-2">
        {downloadLoading ? (
          <Skeleton className="h-full min-h-[400px] w-full" />
        ) : downloadUrl ? (
          <DocumentViewer
            url={downloadUrl}
            filename={activeSource.filename}
            initialPage={activeSource.page ?? undefined}
            highlightText={activeSource.chunk_text}
          />
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
            Unable to load document
          </div>
        )}
      </div>

      {/* Citation nav footer */}
      <div className="space-y-2 border-t px-3 py-3">
        <div className="flex items-center justify-between">
          <span className="text-xs text-muted-foreground">
            Citation {currentIdx + 1} of {allSources.length}
          </span>
          <div className="flex items-center gap-1">
            <Button
              variant="outline"
              size="sm"
              className="h-6 gap-1 px-2 text-[10px]"
              onClick={goToPrev}
              disabled={!hasPrev}
            >
              <ChevronLeft className="h-3 w-3" />
              Prev
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="h-6 gap-1 px-2 text-[10px]"
              onClick={goToNext}
              disabled={!hasNext}
            >
              Next
              <ChevronRight className="h-3 w-3" />
            </Button>
          </div>
        </div>

        <div className="border-l-2 border-amber-500/60 pl-3">
          <p className="line-clamp-3 text-xs leading-relaxed text-foreground/80">
            {activeSource.chunk_text}
          </p>
        </div>

        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            {activeSource.page != null && (
              <Badge variant="secondary" className="text-[10px]">
                Page {activeSource.page}
              </Badge>
            )}
            <Badge variant="secondary" className="text-[10px]">
              {(activeSource.relevance_score * 100).toFixed(0)}% match
            </Badge>
          </div>
          <Button
            variant="ghost"
            size="sm"
            className="h-6 gap-1 px-2 text-[10px]"
            asChild
          >
            <Link to="/documents" search={{ id: activeSource.doc_id ?? activeSource.id }}>
              <ExternalLink className="h-3 w-3" />
              Open in Tab
            </Link>
          </Button>
        </div>
      </div>
    </div>
  );
}

export function CitationSidebar() {
  const { isOpen, mode } = useCitationStore();

  if (!isOpen) return null;

  return mode === "expanded" ? <ExpandedView /> : <CompactView />;
}
