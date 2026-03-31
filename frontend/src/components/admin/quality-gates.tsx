import { CheckCircle2, XCircle } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

interface EvaluationResult {
  metrics: Record<string, number>;
  passed: boolean;
}

interface QualityGatesProps {
  data: EvaluationResult | undefined;
  isLoading: boolean;
}

const THRESHOLDS: Record<string, number> = {
  accuracy: 0.8,
  faithfulness: 0.85,
  relevance: 0.75,
  completeness: 0.7,
  citation_precision: 0.8,
  latency_p95_ms: 5000,
};

function isPassingMetric(name: string, value: number): boolean {
  const threshold = THRESHOLDS[name];
  if (threshold === undefined) return true;
  // latency: lower is better
  if (name.includes("latency")) return value <= threshold;
  return value >= threshold;
}

function formatMetricValue(name: string, value: number): string {
  if (name.includes("latency") || name.includes("ms")) {
    return `${Math.round(value).toLocaleString()}ms`;
  }
  return `${(value * 100).toFixed(1)}%`;
}

export function QualityGates({ data, isLoading }: QualityGatesProps) {
  if (isLoading) {
    return (
      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-4">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-28" />
        ))}
      </div>
    );
  }

  if (!data) {
    return (
      <Card>
        <CardContent className="flex h-32 items-center justify-center">
          <p className="text-sm text-muted-foreground">No evaluation results available.</p>
        </CardContent>
      </Card>
    );
  }

  const entries = Object.entries(data.metrics);

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <h3 className="text-sm font-semibold">Overall</h3>
        <Badge variant={data.passed ? "default" : "destructive"}>
          {data.passed ? "PASSED" : "FAILED"}
        </Badge>
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-4">
        {entries.map(([name, value]) => {
          const passing = isPassingMetric(name, value);
          return (
            <Card key={name}>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center justify-between text-xs font-medium text-muted-foreground">
                  <span className="capitalize">{name.replace(/_/g, " ")}</span>
                  {passing ? (
                    <CheckCircle2 className="h-4 w-4 text-green-500" />
                  ) : (
                    <XCircle className="h-4 w-4 text-red-500" />
                  )}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p
                  className={cn(
                    "text-2xl font-bold",
                    passing ? "text-foreground" : "text-red-500",
                  )}
                >
                  {formatMetricValue(name, value)}
                </p>
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
