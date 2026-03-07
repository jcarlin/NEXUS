import { useState } from "react";
import { ArrowUp, ArrowDown, Minus } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";
import type { EvalRunResponse } from "@/api/generated/schemas";

interface RunComparisonProps {
  runs: EvalRunResponse[];
}

export function RunComparison({ runs }: RunComparisonProps) {
  const [leftId, setLeftId] = useState<string>(runs[1]?.id ?? "");
  const [rightId, setRightId] = useState<string>(runs[0]?.id ?? "");

  const leftRun = runs.find((r) => r.id === leftId);
  const rightRun = runs.find((r) => r.id === rightId);

  const leftMetrics = (leftRun?.metrics ?? {}) as Record<string, number>;
  const rightMetrics = (rightRun?.metrics ?? {}) as Record<string, number>;

  const allMetrics = new Set<string>();
  Object.keys(leftMetrics).forEach((k) => allMetrics.add(k));
  Object.keys(rightMetrics).forEach((k) => allMetrics.add(k));

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-4">
        <div className="flex-1 space-y-1">
          <p className="text-xs font-medium text-muted-foreground">Baseline Run</p>
          <Select value={leftId} onValueChange={setLeftId}>
            <SelectTrigger>
              <SelectValue placeholder="Select run" />
            </SelectTrigger>
            <SelectContent>
              {runs.map((r) => (
                <SelectItem key={r.id} value={r.id}>
                  {r.id.slice(0, 8)} ({r.mode})
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <span className="mt-5 text-sm text-muted-foreground">vs</span>
        <div className="flex-1 space-y-1">
          <p className="text-xs font-medium text-muted-foreground">Comparison Run</p>
          <Select value={rightId} onValueChange={setRightId}>
            <SelectTrigger>
              <SelectValue placeholder="Select run" />
            </SelectTrigger>
            <SelectContent>
              {runs.map((r) => (
                <SelectItem key={r.id} value={r.id}>
                  {r.id.slice(0, 8)} ({r.mode})
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {leftRun && rightRun && (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-3">
          {[...allMetrics].map((metric) => {
            const leftVal = leftMetrics[metric] ?? 0;
            const rightVal = rightMetrics[metric] ?? 0;
            const delta = rightVal - leftVal;
            const isLatency = metric.includes("latency") || metric.includes("ms");
            // For latency, lower is better; for others, higher is better
            const improved = isLatency ? delta < 0 : delta > 0;
            const regressed = isLatency ? delta > 0 : delta < 0;

            return (
              <Card key={metric}>
                <CardHeader className="pb-2">
                  <CardTitle className="text-xs font-medium capitalize text-muted-foreground">
                    {metric.replace(/_/g, " ")}
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="flex items-end justify-between">
                    <div className="text-sm text-muted-foreground">
                      {isLatency
                        ? `${Math.round(leftVal)}ms`
                        : `${(leftVal * 100).toFixed(1)}%`}
                    </div>
                    <div className="text-lg font-bold">
                      {isLatency
                        ? `${Math.round(rightVal)}ms`
                        : `${(rightVal * 100).toFixed(1)}%`}
                    </div>
                  </div>
                  <div
                    className={cn(
                      "mt-1 flex items-center gap-1 text-xs",
                      improved && "text-green-500",
                      regressed && "text-red-500",
                      !improved && !regressed && "text-muted-foreground",
                    )}
                  >
                    {improved ? (
                      <ArrowUp className="h-3 w-3" />
                    ) : regressed ? (
                      <ArrowDown className="h-3 w-3" />
                    ) : (
                      <Minus className="h-3 w-3" />
                    )}
                    {isLatency
                      ? `${delta > 0 ? "+" : ""}${Math.round(delta)}ms`
                      : `${delta > 0 ? "+" : ""}${(delta * 100).toFixed(1)}pp`}
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      {(!leftRun || !rightRun) && (
        <Card>
          <CardContent className="flex h-32 items-center justify-center">
            <p className="text-sm text-muted-foreground">
              Select two runs to compare metrics.
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
