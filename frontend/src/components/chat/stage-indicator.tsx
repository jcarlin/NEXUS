import { Loader2 } from "lucide-react";

const STAGES = [
  { key: "connecting", label: "Connecting..." },
  { key: "resolving_context", label: "Resolving context..." },
  { key: "classifying", label: "Classifying query..." },
  { key: "planning", label: "Planning retrieval..." },
  { key: "rewriting", label: "Rewriting query..." },
  { key: "retrieving", label: "Retrieving documents..." },
  { key: "reranking", label: "Reranking results..." },
  { key: "checking_relevance", label: "Checking relevance..." },
  { key: "graph_lookup", label: "Graph lookup..." },
  { key: "reformulating", label: "Reformulating..." },
  { key: "investigating", label: "Investigating..." },
  { key: "analyzing", label: "Analyzing..." },
  { key: "verifying_citations", label: "Verifying citations..." },
  { key: "generating_follow_ups", label: "Generating follow-ups..." },
  { key: "generating", label: "Generating response..." },
  { key: "synthesizing", label: "Synthesizing answer..." },
  { key: "assessing", label: "Assessing sufficiency..." },
] as const;

const stageLabelMap: Record<string, string> = Object.fromEntries(
  STAGES.map((s) => [s.key, s.label]),
);

interface StageIndicatorProps {
  stage: string;
}

export function StageIndicator({ stage }: StageIndicatorProps) {
  const label = stageLabelMap[stage] ?? stage;
  const currentIdx = STAGES.findIndex((s) => s.key === stage);

  return (
    <div className="space-y-2 px-4 py-3">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
        <span>{label}</span>
      </div>
      {currentIdx >= 0 && (
        <div className="flex gap-1">
          {STAGES.map((s, idx) => (
            <div
              key={s.key}
              className={`h-1 flex-1 rounded-full transition-colors duration-300 ${
                idx < currentIdx
                  ? "bg-primary/60"
                  : idx === currentIdx
                    ? "animate-pulse bg-primary"
                    : "bg-muted"
              }`}
            />
          ))}
        </div>
      )}
    </div>
  );
}
