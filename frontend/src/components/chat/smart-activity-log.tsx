import { ActivityLog } from "@/components/chat/activity-log";
import { TracePanel } from "@/components/chat/trace-panel";
import { useDevModeStore } from "@/stores/dev-mode-store";
import type { ToolCallEntry, TraceStep, TraceSummary } from "@/types";

interface SmartActivityLogProps {
  toolCalls: ToolCallEntry[];
  traceSteps: TraceStep[];
  traceSummary: TraceSummary | null;
  stage: string | null;
  isStreaming: boolean;
}

export function SmartActivityLog({
  toolCalls,
  traceSteps,
  traceSummary,
  stage,
  isStreaming,
}: SmartActivityLogProps) {
  const devMode = useDevModeStore((s) => s.enabled);

  if (devMode && traceSteps.length > 0) {
    return (
      <TracePanel
        traceSteps={traceSteps}
        traceSummary={traceSummary}
        toolCalls={toolCalls}
        stage={stage}
        isStreaming={isStreaming}
      />
    );
  }

  return <ActivityLog toolCalls={toolCalls} stage={stage} isStreaming={isStreaming} />;
}
