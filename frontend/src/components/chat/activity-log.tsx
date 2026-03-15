import { useState, useEffect } from "react";
import { Check, Loader2, ChevronRight, Circle } from "lucide-react";
import type { ToolCallEntry } from "@/types";

const PHASES = [
  {
    label: "Understanding your question",
    stages: [
      "connecting",
      "resolving_context",
      "classifying",
      "planning",
      "rewriting",
      "awaiting_clarification",
      "resuming",
    ],
  },
  {
    label: "Searching documents",
    stages: [
      "retrieving",
      "reranking",
      "checking_relevance",
      "graph_lookup",
      "reformulating",
    ],
  },
  {
    label: "Analyzing sources",
    stages: [
      "investigating",
      "analyzing",
      "verifying_citations",
      "extracting_results",
      "checking_entity_grounding",
      "assessing",
    ],
  },
  {
    label: "Writing response",
    stages: ["generating", "synthesizing", "generating_follow_ups"],
  },
] as const;

function getPhaseIndex(stage: string): number {
  for (let i = 0; i < PHASES.length; i++) {
    if ((PHASES[i]!.stages as readonly string[]).includes(stage)) return i;
  }
  return 0;
}

function StepIcon({ kind }: { kind?: string }) {
  if (kind === "step") {
    return <Circle className="h-2 w-2 fill-muted-foreground/40 text-muted-foreground/40 shrink-0" />;
  }
  return <Check className="h-3 w-3 text-primary/70 shrink-0" />;
}

interface ActivityLogProps {
  toolCalls: ToolCallEntry[];
  stage: string | null;
  isStreaming: boolean;
}

export function ActivityLog({ toolCalls, stage, isStreaming }: ActivityLogProps) {
  const [expanded, setExpanded] = useState(false);

  // Auto-expand while streaming, collapse when done
  useEffect(() => {
    if (!isStreaming && stage === null) {
      setExpanded(false);
    }
  }, [isStreaming, stage]);

  const phaseIdx = stage ? getPhaseIndex(stage) : PHASES.length - 1;
  const phaseLabel = stage ? (PHASES[phaseIdx]?.label ?? "Processing...") : null;

  // For collapsed summary, only show tool calls (not pipeline steps)
  const toolCallsOnly = toolCalls.filter((tc) => tc.kind !== "step");
  const summaryLabel =
    toolCallsOnly.length > 0
      ? toolCallsOnly.map((tc) => tc.label).join(", ")
      : toolCalls.map((tc) => tc.label).join(", ");

  // While streaming: show live view
  if (isStreaming || stage) {
    return (
      <div className="flex justify-start" data-testid="activity-log">
        <div className="rounded-2xl bg-muted/50 px-4 py-3 space-y-2.5 min-w-[260px]">
          {/* Current phase label */}
          {phaseLabel && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
              <span>{phaseLabel}</span>
            </div>
          )}

          {/* Tool call log */}
          {toolCalls.length > 0 && (
            <div className="space-y-1" data-testid="activity-log-steps">
              {toolCalls.map((tc, idx) => (
                <div
                  key={`${tc.tool}-${idx}`}
                  className={`flex items-center gap-2 text-xs ${
                    tc.kind === "step"
                      ? "text-muted-foreground/60"
                      : "text-muted-foreground"
                  }`}
                >
                  <StepIcon kind={tc.kind} />
                  <span>{tc.label}</span>
                </div>
              ))}
            </div>
          )}

          {/* Progress bar */}
          {stage && (
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
          )}
        </div>
      </div>
    );
  }

  // After completion: collapsed summary
  if (toolCalls.length === 0) return null;

  return (
    <div className="flex justify-start" data-testid="activity-log">
      <button
        type="button"
        className="rounded-2xl bg-muted/50 px-4 py-2.5 text-left transition-colors hover:bg-muted/70 min-w-[200px]"
        onClick={() => setExpanded(!expanded)}
        data-testid="activity-log-toggle"
      >
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <ChevronRight
            className={`h-3 w-3 shrink-0 transition-transform duration-200 ${
              expanded ? "rotate-90" : ""
            }`}
          />
          <span className="font-medium">
            {expanded ? "Analysis steps" : summaryLabel}
          </span>
        </div>

        {expanded && (
          <div className="mt-2 space-y-1 pl-[18px]" data-testid="activity-log-expanded">
            {toolCalls.map((tc, idx) => (
              <div
                key={`${tc.tool}-${idx}`}
                className={`flex items-center gap-2 text-xs ${
                  tc.kind === "step"
                    ? "text-muted-foreground/60"
                    : "text-muted-foreground"
                }`}
              >
                <StepIcon kind={tc.kind} />
                <span>{tc.label}</span>
              </div>
            ))}
          </div>
        )}
      </button>
    </div>
  );
}
