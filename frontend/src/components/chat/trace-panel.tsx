import { useState } from "react";
import { ChevronRight, Clock, Cpu, Search, Zap, Loader2 } from "lucide-react";
import type { TraceStep, TraceSummary, ToolCallEntry } from "@/types";
import { cn } from "@/lib/utils";

const KIND_ICONS: Record<string, typeof Clock> = {
  step: Cpu,
  tool: Search,
  llm: Zap,
};

const KIND_COLORS: Record<string, string> = {
  step: "text-blue-500",
  tool: "text-amber-500",
  llm: "text-purple-500",
};

function formatMs(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function formatArgs(args: Record<string, unknown>): string {
  return Object.entries(args)
    .map(([k, v]) => {
      if (typeof v === "boolean") return `${k}=${v ? "ON" : "OFF"}`;
      return `${k}=${v}`;
    })
    .join(", ");
}

interface TracePanelProps {
  traceSteps: TraceStep[];
  traceSummary: TraceSummary | null;
  toolCalls: ToolCallEntry[];
  stage: string | null;
  isStreaming: boolean;
}

export function TracePanel({ traceSteps, traceSummary, toolCalls, stage, isStreaming }: TracePanelProps) {
  const [expanded, setExpanded] = useState(false);

  const hasTrace = traceSteps.length > 0;
  const summary = traceSummary;
  const totalMs = summary?.total_ms ?? traceSteps.reduce((acc, s) => acc + (s.duration_ms || 0), 0);
  const toolCount = traceSteps.filter((s) => s.kind === "tool").length;
  const overrideCount = new Set(traceSteps.flatMap((s) => s.overrides_active ?? [])).size;

  // While streaming: show live trace steps
  if (isStreaming || stage) {
    return (
      <div className="flex justify-start" data-testid="trace-panel">
        <div className="rounded-2xl bg-muted/50 px-4 py-3 space-y-2 min-w-[280px] max-w-[480px]">
          {/* Header with spinner */}
          {stage && (
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Loader2 className="h-3 w-3 animate-spin text-primary" />
              <span className="font-medium">Pipeline trace</span>
              {hasTrace && (
                <span className="ml-auto font-mono text-[10px] tabular-nums">
                  {formatMs(totalMs)}
                </span>
              )}
            </div>
          )}

          {/* Live trace steps */}
          {traceSteps.map((step, idx) => {
            const Icon = KIND_ICONS[step.kind] ?? Cpu;
            const color = KIND_COLORS[step.kind] ?? "text-muted-foreground";

            return (
              <div key={`${step.node}-${idx}`} className="flex items-start gap-2 text-xs">
                <Icon className={cn("h-3 w-3 mt-0.5 shrink-0", color)} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-medium truncate">{step.label}</span>
                    <span className="font-mono text-[10px] text-muted-foreground/70 tabular-nums shrink-0">
                      {formatMs(step.duration_ms)}
                    </span>
                  </div>
                  {step.args_summary && Object.keys(step.args_summary).length > 0 && (
                    <p className="text-[10px] text-muted-foreground/60 truncate">
                      {formatArgs(step.args_summary)}
                    </p>
                  )}
                  {step.overrides_active && step.overrides_active.length > 0 && (
                    <div className="flex gap-1 mt-0.5 flex-wrap">
                      {step.overrides_active.map((o) => (
                        <span
                          key={o}
                          className="inline-block rounded bg-primary/10 px-1 py-0 text-[9px] font-medium text-primary"
                        >
                          {o.replace("enable_", "").replace(/_/g, " ")}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            );
          })}

          {/* Waiting spinner for tool calls not yet in trace */}
          {toolCalls.length > traceSteps.length && (
            <div className="flex items-center gap-2 text-xs text-muted-foreground/60">
              <Loader2 className="h-3 w-3 animate-spin" />
              <span>{toolCalls[toolCalls.length - 1]?.label}</span>
            </div>
          )}
        </div>
      </div>
    );
  }

  // After completion: collapsed summary
  if (!hasTrace) return null;

  return (
    <div className="flex justify-start" data-testid="trace-panel">
      <button
        type="button"
        className="rounded-2xl bg-muted/50 px-4 py-2.5 text-left transition-colors hover:bg-muted/70 min-w-[240px] max-w-[520px]"
        onClick={() => setExpanded(!expanded)}
        data-testid="trace-panel-toggle"
      >
        {/* Summary line */}
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <ChevronRight
            className={cn("h-3 w-3 shrink-0 transition-transform duration-200", expanded && "rotate-90")}
          />
          <span className="font-medium">Trace</span>
          <span className="font-mono text-[10px] tabular-nums">{formatMs(totalMs)}</span>
          <span className="text-muted-foreground/50">·</span>
          <span className="text-[10px]">{traceSteps.length} steps</span>
          {toolCount > 0 && (
            <>
              <span className="text-muted-foreground/50">·</span>
              <span className="text-[10px]">{toolCount} tools</span>
            </>
          )}
          {overrideCount > 0 && (
            <>
              <span className="text-muted-foreground/50">·</span>
              <span className="text-[10px] text-primary">{overrideCount} overrides</span>
            </>
          )}
        </div>

        {/* Expanded timeline */}
        {expanded && (
          <div className="mt-2.5 space-y-1.5 pl-[18px]" data-testid="trace-panel-expanded">
            {traceSteps.map((step, idx) => {
              const Icon = KIND_ICONS[step.kind] ?? Cpu;
              const color = KIND_COLORS[step.kind] ?? "text-muted-foreground";
              const hasOverrides = step.overrides_active && step.overrides_active.length > 0;

              return (
                <div
                  key={`${step.node}-${idx}`}
                  className={cn(
                    "flex items-start gap-2 text-xs",
                    hasOverrides && "border-l-2 border-primary/40 pl-2 -ml-2",
                  )}
                >
                  <Icon className={cn("h-3 w-3 mt-0.5 shrink-0", color)} />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-muted-foreground">{step.label}</span>
                      <span className="font-mono text-[10px] text-muted-foreground/60 tabular-nums shrink-0">
                        {formatMs(step.duration_ms)}
                      </span>
                    </div>
                    {step.args_summary && Object.keys(step.args_summary).length > 0 && (
                      <p className="text-[10px] text-muted-foreground/50 truncate">
                        {formatArgs(step.args_summary)}
                      </p>
                    )}
                    {step.result_summary && Object.keys(step.result_summary).length > 0 && (
                      <p className="text-[10px] text-muted-foreground/50">
                        → {formatArgs(step.result_summary)}
                      </p>
                    )}
                    {step.tokens && (
                      <p className="text-[10px] text-purple-400/70">
                        {step.tokens.input.toLocaleString()} in / {step.tokens.output.toLocaleString()} out
                      </p>
                    )}
                    {hasOverrides && (
                      <div className="flex gap-1 mt-0.5 flex-wrap">
                        {step.overrides_active!.map((o) => (
                          <span
                            key={o}
                            className="inline-block rounded bg-primary/10 px-1 py-0 text-[9px] font-medium text-primary"
                          >
                            {o.replace("enable_", "").replace(/_/g, " ")}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}

            {/* Bottom summary */}
            <div className="mt-2 border-t border-muted-foreground/10 pt-1.5 text-[10px] text-muted-foreground/60">
              Total: {formatMs(totalMs)}
              {overrideCount > 0 && (
                <span className="ml-2">
                  Active overrides: {Array.from(new Set(traceSteps.flatMap((s) => s.overrides_active ?? []))).join(", ")}
                </span>
              )}
            </div>
          </div>
        )}
      </button>
    </div>
  );
}
