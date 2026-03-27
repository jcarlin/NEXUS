import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
import { useAppStore } from "@/stores/app-store";
import { useLiveRefresh } from "@/hooks/use-live-refresh";
import { formatDateTime } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

interface ErrorCategoryBreakdown {
  category: string;
  count: number;
}

interface FailureRatePoint {
  timestamp: string;
  completed: number;
  failed: number;
}

interface TopError {
  error_summary: string;
  category: string | null;
  count: number;
  last_seen: string;
}

interface StageFailure {
  stage: string;
  count: number;
}

interface FailureAnalysis {
  category_breakdown: ErrorCategoryBreakdown[];
  failure_rate: FailureRatePoint[];
  top_errors: TopError[];
  stage_distribution: StageFailure[];
  total_failed: number;
  total_completed: number;
}

const TIME_WINDOWS = [
  { label: "24h", hours: 24 },
  { label: "7d", hours: 168 },
  { label: "30d", hours: 720 },
] as const;

const CATEGORY_COLORS: Record<string, string> = {
  TIMEOUT: "bg-red-500",
  OOM: "bg-red-700",
  PARSE_ERROR: "bg-blue-500",
  NETWORK: "bg-amber-500",
  LLM_API: "bg-amber-600",
  VALIDATION: "bg-purple-500",
  STORAGE: "bg-orange-500",
  UNKNOWN: "bg-muted-foreground",
};

function HorizontalBar({
  items,
  colorMap,
}: {
  items: { label: string; count: number }[];
  colorMap: Record<string, string>;
}) {
  const maxCount = Math.max(...items.map((i) => i.count), 1);
  return (
    <div className="space-y-2">
      {items.map((item) => (
        <div key={item.label} className="flex items-center gap-2">
          <span className="w-24 truncate text-xs text-muted-foreground text-right">
            {item.label}
          </span>
          <div className="flex-1 h-5 bg-muted rounded-sm overflow-hidden">
            <div
              className={`h-full rounded-sm ${colorMap[item.label] ?? "bg-muted-foreground"}`}
              style={{ width: `${(item.count / maxCount) * 100}%` }}
            />
          </div>
          <span className="w-10 text-xs tabular-nums text-right">
            {item.count}
          </span>
        </div>
      ))}
      {items.length === 0 && (
        <p className="text-xs text-muted-foreground text-center py-4">
          No failures in this time window.
        </p>
      )}
    </div>
  );
}

export function FailureAnalysis() {
  const matterId = useAppStore((s) => s.matterId);
  const { isLive } = useLiveRefresh();
  const [hours, setHours] = useState(168);

  const { data, isLoading } = useQuery({
    queryKey: ["pipeline-failure-analysis", matterId, hours],
    queryFn: () =>
      apiClient<FailureAnalysis>({
        url: "/api/v1/admin/pipeline/failure-analysis",
        method: "GET",
        params: { hours },
      }),
    enabled: !!matterId,
    refetchInterval: isLive ? 60_000 : false,
  });

  if (isLoading) {
    return (
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-48" />
        ))}
      </div>
    );
  }

  const analysis = data;
  const failureRate =
    analysis && analysis.total_failed + analysis.total_completed > 0
      ? ((analysis.total_failed / (analysis.total_failed + analysis.total_completed)) * 100).toFixed(1)
      : "0";

  return (
    <div className="space-y-4">
      {/* Time window selector + summary */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1">
            {TIME_WINDOWS.map((tw) => (
              <Button
                key={tw.hours}
                size="sm"
                variant={hours === tw.hours ? "default" : "outline"}
                className="h-7 text-xs"
                onClick={() => setHours(tw.hours)}
              >
                {tw.label}
              </Button>
            ))}
          </div>
          {analysis && (
            <div className="flex items-center gap-3 text-xs text-muted-foreground">
              <span>
                <strong className="text-destructive">{analysis.total_failed}</strong> failed
              </span>
              <span>
                <strong className="text-green-600">{analysis.total_completed}</strong> completed
              </span>
              <span>
                <strong>{failureRate}%</strong> failure rate
              </span>
            </div>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Error Category Breakdown */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium">
              Error Categories
            </CardTitle>
          </CardHeader>
          <CardContent>
            <HorizontalBar
              items={(analysis?.category_breakdown ?? []).map((c) => ({
                label: c.category,
                count: c.count,
              }))}
              colorMap={CATEGORY_COLORS}
            />
          </CardContent>
        </Card>

        {/* Stage Failure Distribution */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium">
              Failures by Stage
            </CardTitle>
          </CardHeader>
          <CardContent>
            <HorizontalBar
              items={(analysis?.stage_distribution ?? []).map((s) => ({
                label: s.stage,
                count: s.count,
              }))}
              colorMap={{
                parsing: "bg-blue-500",
                chunking: "bg-cyan-500",
                embedding: "bg-green-500",
                extracting: "bg-purple-500",
                indexing: "bg-orange-500",
                failed: "bg-red-500",
              }}
            />
          </CardContent>
        </Card>

        {/* Failure Rate Timeline */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium">
              Success vs Failure Over Time
            </CardTitle>
          </CardHeader>
          <CardContent>
            {analysis && analysis.failure_rate.length > 0 ? (
              <div className="flex items-end gap-px h-32">
                {analysis.failure_rate.map((point, i) => {
                  const total = point.completed + point.failed;
                  if (total === 0) return null;
                  const failPct = (point.failed / total) * 100;
                  const maxTotal = Math.max(
                    ...analysis.failure_rate.map((p) => p.completed + p.failed),
                  );
                  const barHeight = (total / maxTotal) * 100;
                  return (
                    <div
                      key={i}
                      className="flex-1 flex flex-col justify-end min-w-[2px]"
                      title={`${new Date(point.timestamp).toLocaleString()}\n${point.completed} ok, ${point.failed} failed`}
                    >
                      <div
                        className="w-full rounded-t-sm overflow-hidden"
                        style={{ height: `${barHeight}%` }}
                      >
                        <div
                          className="w-full bg-red-500"
                          style={{ height: `${failPct}%` }}
                        />
                        <div
                          className="w-full bg-green-500"
                          style={{ height: `${100 - failPct}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="text-xs text-muted-foreground text-center py-8">
                No data in this time window.
              </p>
            )}
          </CardContent>
        </Card>

        {/* Top Errors */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium">Top Errors</CardTitle>
          </CardHeader>
          <CardContent className="px-0">
            {analysis && analysis.top_errors.length > 0 ? (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="text-xs">Error</TableHead>
                    <TableHead className="text-xs w-20">Category</TableHead>
                    <TableHead className="text-xs w-12 text-right">Count</TableHead>
                    <TableHead className="text-xs w-28">Last Seen</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {analysis.top_errors.map((err, i) => (
                    <TableRow key={i}>
                      <TableCell className="font-mono text-[10px] max-w-[300px] truncate" title={err.error_summary}>
                        {err.error_summary}
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant="secondary"
                          className="text-[9px]"
                        >
                          {err.category ?? "UNKNOWN"}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right tabular-nums text-xs">
                        {err.count}
                      </TableCell>
                      <TableCell className="text-[10px] text-muted-foreground whitespace-nowrap">
                        {formatDateTime(err.last_seen)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            ) : (
              <p className="text-xs text-muted-foreground text-center py-8">
                No errors in this time window.
              </p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
