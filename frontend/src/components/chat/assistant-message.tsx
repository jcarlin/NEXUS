import { useState, Fragment, useCallback } from "react";
import {
  ChevronDown,
  ChevronUp,
  FileText,
  ShieldCheck,
  ShieldAlert,
  ShieldQuestion,
  Plus,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { CitationMarker } from "./citation-marker";
import { EntityChips } from "./entity-chips";
import { QuickViewModal } from "@/components/documents/quick-view-modal";
import { useAppStore } from "@/stores/app-store";
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

/** Parse text with [N] citation markers into React nodes. */
function renderWithCitations(
  text: string,
  sources: SourceDocument[],
  onQuickView?: (source: SourceDocument) => void,
) {
  const parts = text.split(/(\[\d+\])/g);
  return parts.map((part, i) => {
    const match = part.match(/^\[(\d+)\]$/);
    if (match) {
      const idx = parseInt(match[1]!, 10) - 1;
      const source = sources[idx];
      if (source) {
        return (
          <CitationMarker
            key={i}
            index={idx}
            source={source}
            onQuickView={onQuickView}
          />
        );
      }
    }
    return <Fragment key={i}>{part}</Fragment>;
  });
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

  const handleQuickView = useCallback((source: SourceDocument) => {
    setSelectedSource(source);
  }, []);

  return (
    <div className="flex justify-start" data-testid="assistant-message">
      <div className="max-w-[85%] space-y-2">
        <Card>
          <CardContent className="p-3">
            <div className="whitespace-pre-wrap text-sm leading-relaxed">
              {renderWithCitations(content, sources, handleQuickView)}
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

        {sources.length > 0 && (
          <div className="rounded-md border" data-testid="source-panel">
            <button
              onClick={() => setSourcesOpen(!sourcesOpen)}
              className="flex w-full items-center justify-between px-3 py-2 text-xs font-medium text-muted-foreground hover:bg-accent"
            >
              <span className="flex items-center gap-1.5">
                <FileText className="h-3.5 w-3.5" />
                {sources.length} source{sources.length !== 1 ? "s" : ""}
              </span>
              {sourcesOpen ? (
                <ChevronUp className="h-3.5 w-3.5" />
              ) : (
                <ChevronDown className="h-3.5 w-3.5" />
              )}
            </button>
            {sourcesOpen && (
              <div className="space-y-1 border-t px-3 py-2">
                {sources.map((src, idx) => (
                  <button
                    key={src.id}
                    type="button"
                    className="flex w-full items-start gap-2 rounded-md p-1.5 text-left text-xs transition-colors hover:bg-accent"
                    onClick={() => handleQuickView(src)}
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
            )}
          </div>
        )}

        {citedClaims.length > 0 && (
          <div className="rounded-md border">
            <button
              onClick={() => setClaimsOpen(!claimsOpen)}
              className="flex w-full items-center justify-between px-3 py-2 text-xs font-medium text-muted-foreground hover:bg-accent"
            >
              <span>
                {citedClaims.length} cited claim
                {citedClaims.length !== 1 ? "s" : ""}
              </span>
              {claimsOpen ? (
                <ChevronUp className="h-3.5 w-3.5" />
              ) : (
                <ChevronDown className="h-3.5 w-3.5" />
              )}
            </button>
            {claimsOpen && (
              <div className="space-y-2 border-t px-3 py-2">
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
            )}
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
