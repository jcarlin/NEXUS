import { Loader2 } from "lucide-react";

const stageLabels: Record<string, string> = {
  connecting: "Connecting...",
  classifying: "Classifying query...",
  planning: "Planning retrieval strategy...",
  rewriting: "Rewriting query...",
  retrieving: "Retrieving relevant documents...",
  reranking: "Reranking results...",
  generating: "Generating response...",
  synthesizing: "Synthesizing answer...",
  assessing: "Assessing sufficiency...",
};

interface StageIndicatorProps {
  stage: string;
}

export function StageIndicator({ stage }: StageIndicatorProps) {
  const label = stageLabels[stage] ?? stage;

  return (
    <div className="flex items-center gap-2 px-4 py-2 text-sm text-muted-foreground">
      <Loader2 className="h-3.5 w-3.5 animate-spin" />
      <span>{label}</span>
    </div>
  );
}
