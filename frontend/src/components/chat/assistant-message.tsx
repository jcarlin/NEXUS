import { useState, useCallback } from "react";
import {
  ChevronDown,
  ChevronUp,
  FileText,
  ShieldCheck,
  ShieldAlert,
  ShieldQuestion,
  Plus,
  BookOpen,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { MarkdownMessage } from "./markdown-message";
import { EntityChips } from "./entity-chips";
import { QuickViewModal } from "@/components/documents/quick-view-modal";
import { useAppStore } from "@/stores/app-store";
import { useCitationStore } from "@/stores/citation-store";
import type {
  SourceDocument,
  EntityMention,
  CitedClaim,
} from "@/types";

interface AssistantMessageProps {
  content: string;
  sources: SourceDocument[];
  entities: EntityMention[];
  citedClaims?: CitedClaim[];
  isStreaming?: boolean;
}

const verificationIcon = {
  verified: ShieldCheck,
  flagged: ShieldAlert,
  unverified: ShieldQuestion,
};

const verificationColor = {
  verified: "text-green-600",
  flagged: "text-red-600",
  unverified: "text-muted-foreground",
};

export function AssistantMessage({
  content,
  sources,
  entities,
  citedClaims = [],
  isStreaming,
}: AssistantMessageProps) {
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const [claimsOpen, setClaimsOpen] = useState(false);
  const [selectedSource, setSelectedSource] = useState<SourceDocument | null>(null);
  const addFinding = useAppStore((s) => s.addFinding);
  const openWithSources = useCitationStore((s) => s.openWithSources);

  const handleCitationClick = useCallback(
    (source: SourceDocument, _index: number) => {
      openWithSources(sources, citedClaims, source);
    },
    [sources, citedClaims, openWithSources],
  );

  const handleViewSources = useCallback(() => {
    openWithSources(sources, citedClaims);
  }, [sources, citedClaims, openWithSources]);

  return (
    <div className="flex justify-start" data-testid="assistant-message">
      <div className="space-y-2">
        <Card>
          <CardContent className="p-4">
            <div className="text-sm">
              <MarkdownMessage
                content={content}
                sources={sources}
                onCitationClick={handleCitationClick}
              />
              {isStreaming && (
                <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse bg-foreground/70" />
              )}
            </div>
          </CardContent>
        </Card>

        {entities.length > 0 && (
          <div className="px-1">
            <EntityChips entities={entities} />
          </div>
        )}

        <div className="flex items-center gap-2 px-1">
          {sources.length > 0 && (
            <>
              <Button
                variant="ghost"
                size="sm"
                className="h-7 gap-1.5 text-xs text-muted-foreground"
                onClick={handleViewSources}
              >
                <BookOpen className="h-3.5 w-3.5" />
                {sources.length} source{sources.length !== 1 ? "s" : ""}
              </Button>

              <Button
                variant="ghost"
                size="sm"
                className="h-7 gap-1.5 text-xs text-muted-foreground"
                onClick={() => setSourcesOpen(!sourcesOpen)}
              >
                <FileText className="h-3.5 w-3.5" />
                {sourcesOpen ? (
                  <ChevronUp className="h-3 w-3" />
                ) : (
                  <ChevronDown className="h-3 w-3" />
                )}
              </Button>
            </>
          )}

          {citedClaims.length > 0 && (
            <Button
              variant="ghost"
              size="sm"
              className="h-7 gap-1.5 text-xs text-muted-foreground"
              onClick={() => setClaimsOpen(!claimsOpen)}
            >
              {citedClaims.length} claim{citedClaims.length !== 1 ? "s" : ""}
              {claimsOpen ? (
                <ChevronUp className="h-3 w-3" />
              ) : (
                <ChevronDown className="h-3 w-3" />
              )}
            </Button>
          )}
        </div>

        {sourcesOpen && sources.length > 0 && (
          <div className="rounded-md border" data-testid="source-panel">
            <div className="space-y-1 px-3 py-2">
              {sources.map((src, idx) => (
                <button
                  key={src.id}
                  type="button"
                  className="flex w-full items-start gap-2 rounded-md p-1.5 text-left text-xs transition-colors hover:bg-accent"
                  onClick={() => {
                    openWithSources(sources, citedClaims, src);
                  }}
                >
                  <span className="mt-0.5 flex h-4 min-w-4 items-center justify-center rounded bg-primary/15 text-[10px] font-semibold text-primary">
                    {idx + 1}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium">{src.filename}</p>
                    {src.page != null && (
                      <span className="text-muted-foreground">
                        Page {src.page}
                      </span>
                    )}
                    <p className="mt-0.5 line-clamp-2 text-muted-foreground">
                      {src.chunk_text}
                    </p>
                  </div>
                  <Badge variant="secondary" className="shrink-0 text-[10px]">
                    {(src.relevance_score * 100).toFixed(0)}%
                  </Badge>
                </button>
              ))}
            </div>
          </div>
        )}

        {claimsOpen && citedClaims.length > 0 && (
          <div className="rounded-md border">
            <div className="space-y-2 px-3 py-2">
              {citedClaims.map((claim, idx) => {
                const Icon = verificationIcon[claim.verification_status];
                const color = verificationColor[claim.verification_status];
                return (
                  <div
                    key={idx}
                    className="flex items-start gap-2 text-xs"
                  >
                    <Icon className={`mt-0.5 h-3.5 w-3.5 shrink-0 ${color}`} />
                    <div className="min-w-0 flex-1">
                      <p>{claim.claim_text}</p>
                      <p className="mt-0.5 text-muted-foreground">
                        {claim.filename}
                        {claim.page_number != null &&
                          `, p.${claim.page_number}`}
                        {" "}
                        &middot; Score:{" "}
                        {(claim.grounding_score * 100).toFixed(0)}%
                      </p>
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-6 shrink-0 px-1.5 text-[10px]"
                      onClick={() => addFinding(claim)}
                      title="Add to findings"
                    >
                      <Plus className="mr-0.5 h-3 w-3" />
                      Finding
                    </Button>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {selectedSource && (
          <QuickViewModal
            open={!!selectedSource}
            onOpenChange={(open) => { if (!open) setSelectedSource(null); }}
            documentId={selectedSource.id}
            filename={selectedSource.filename}
            page={selectedSource.page}
            excerpt={selectedSource.chunk_text}
            score={selectedSource.relevance_score}
            downloadUrl={selectedSource.download_url ?? undefined}
            documentType={undefined}
          />
        )}
      </div>
    </div>
  );
}
