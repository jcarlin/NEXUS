import { useState } from "react";
import { X, FileText, ExternalLink, Eye } from "lucide-react";
import { Link } from "@tanstack/react-router";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { QuickViewModal } from "@/components/documents/quick-view-modal";
import { useCitationStore } from "@/stores/citation-store";

export function CitationSidebar() {
  const { isOpen, activeSource, allSources, close, setActiveSource } =
    useCitationStore();
  const [viewerSource, setViewerSource] = useState<typeof activeSource>(null);

  if (!isOpen) return null;

  return (
    <>
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

                  {/* Chunk excerpt */}
                  <div>
                    <p className="mb-1 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                      Excerpt
                    </p>
                    <p className="rounded-md bg-muted/50 p-3 text-xs leading-relaxed text-foreground/80">
                      {activeSource.chunk_text}
                    </p>
                  </div>

                  {/* Actions */}
                  <div className="flex flex-col gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      className="justify-start gap-2 text-xs"
                      onClick={() => setViewerSource(activeSource)}
                    >
                      <Eye className="h-3.5 w-3.5" />
                      Open Viewer
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      className="justify-start gap-2 text-xs"
                      asChild
                    >
                      <Link to="/documents" search={{ id: activeSource.id }}>
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

      {/* QuickViewModal triggered from sidebar */}
      {viewerSource && (
        <QuickViewModal
          open={!!viewerSource}
          onOpenChange={(open) => {
            if (!open) setViewerSource(null);
          }}
          documentId={viewerSource.id}
          filename={viewerSource.filename}
          page={viewerSource.page}
          excerpt={viewerSource.chunk_text}
          score={viewerSource.relevance_score}
          downloadUrl={viewerSource.download_url ?? undefined}
          documentType={undefined}
        />
      )}
    </>
  );
}
