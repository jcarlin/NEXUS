import { Loader2 } from "lucide-react";

const PHASES = [
  { label: "Understanding your question", stages: ["connecting", "resolving_context", "classifying", "planning", "rewriting", "awaiting_clarification", "resuming"] },
  { label: "Searching documents", stages: ["retrieving", "reranking", "checking_relevance", "graph_lookup", "reformulating"] },
  { label: "Analyzing sources", stages: ["investigating", "analyzing", "verifying_citations", "assessing"] },
  { label: "Writing response", stages: ["generating", "synthesizing", "generating_follow_ups"] },
] as const;

function getPhaseIndex(stage: string): number {
  for (let i = 0; i < PHASES.length; i++) {
    if ((PHASES[i]!.stages as readonly string[]).includes(stage)) return i;
  }
  return 0;
}

interface StageIndicatorProps {
  stage: string;
}

export function StageIndicator({ stage }: StageIndicatorProps) {
  const phaseIdx = getPhaseIndex(stage);
  const label = PHASES[phaseIdx]?.label ?? "Processing...";

  return (
    <div className="flex justify-start">
      <div className="rounded-2xl bg-muted/50 px-4 py-3 space-y-2.5">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
          <span>{label}</span>
        </div>
        <div className="flex gap-1.5">
          {PHASES.map((phase, idx) => (
            <div
              key={phase.label}
              className={`h-1 w-8 rounded-full transition-colors duration-500 ${
                idx < phaseIdx
                  ? "bg-primary/60"
                  : idx === phaseIdx
                    ? "animate-pulse bg-primary"
                    : "bg-muted-foreground/20"
              }`}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
