import { useQuery } from "@tanstack/react-query";
import { Activity, AlertTriangle, Clock, Layers, Users } from "lucide-react";
import { apiClient } from "@/api/client";
import { useAppStore } from "@/stores/app-store";
import { useLiveRefresh } from "@/hooks/use-live-refresh";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { PaginatedResponse } from "@/types";

interface CeleryOverview {
  workers: { hostname: string; status: string }[];
  queues: { name: string; reserved_count: number; scheduled_count: number; pending_count?: number }[];
}

interface BulkImportItem {
  status: string;
  estimated_remaining_seconds: number | null;
}

export function PipelineSummary() {
  const matterId = useAppStore((s) => s.matterId);
  const { isLive } = useLiveRefresh();

  const { data: processingData, isLoading: processingLoading } = useQuery({
    queryKey: ["pipeline-processing-count", matterId],
    queryFn: () =>
      apiClient<PaginatedResponse<{ id: string }>>({
        url: "/api/v1/jobs",
        method: "GET",
        params: { status: "processing", limit: 1 },
      }),
    enabled: !!matterId,
    refetchInterval: isLive ? 5_000 : false,
  });

  const { data: failedData, isLoading: failedLoading } = useQuery({
    queryKey: ["pipeline-failed-count", matterId],
    queryFn: () =>
      apiClient<PaginatedResponse<{ id: string }>>({
        url: "/api/v1/jobs",
        method: "GET",
        params: { status: "failed", limit: 1 },
      }),
    enabled: !!matterId,
    refetchInterval: isLive ? 30_000 : false,
  });

  const { data: celeryData, isLoading: celeryLoading } = useQuery({
    queryKey: ["admin-celery"],
    queryFn: () =>
      apiClient<CeleryOverview>({
        url: "/api/v1/admin/operations/celery",
        method: "GET",
      }),
    refetchInterval: isLive ? 10_000 : false,
  });

  const { data: importsData, isLoading: importsLoading } = useQuery({
    queryKey: ["pipeline-imports-eta", matterId],
    queryFn: () =>
      apiClient<PaginatedResponse<BulkImportItem>>({
        url: "/api/v1/bulk-imports",
        method: "GET",
        params: { limit: 5 },
      }),
    enabled: !!matterId,
    refetchInterval: isLive ? 10_000 : false,
  });

  const processingCount = processingData?.total ?? 0;
  const failedCount = failedData?.total ?? 0;

  const queuedCount = (celeryData?.queues ?? []).reduce(
    (sum, q) => sum + (q.pending_count ?? 0) + q.reserved_count + q.scheduled_count,
    0,
  );

  const workers = celeryData?.workers ?? [];
  const onlineCount = workers.filter((w) => w.status === "online").length;
  const totalWorkers = workers.length;

  const activeImports = (importsData?.items ?? []).filter(
    (i) => i.status === "processing",
  );
  const maxEta = activeImports.reduce((max, i) => {
    const eta = i.estimated_remaining_seconds ?? 0;
    return eta > max ? eta : max;
  }, 0);

  function formatEta(seconds: number): string {
    if (seconds <= 0) return "--";
    if (seconds < 60) return `~${Math.ceil(seconds)}s`;
    if (seconds < 3600) return `~${Math.ceil(seconds / 60)}m`;
    const hours = Math.floor(seconds / 3600);
    const mins = Math.round((seconds % 3600) / 60);
    return mins > 0 ? `~${hours}h ${mins}m` : `~${hours}h`;
  }

  const stats = [
    {
      label: "Processing",
      value: processingCount,
      loading: processingLoading,
      icon: Activity,
      color: processingCount > 0 ? "text-blue-500" : "text-muted-foreground",
    },
    {
      label: "Failed",
      value: failedCount,
      loading: failedLoading,
      icon: AlertTriangle,
      color: failedCount > 0 ? "text-destructive" : "text-muted-foreground",
    },
    {
      label: "Queued",
      value: queuedCount,
      loading: celeryLoading,
      icon: Layers,
      color: "text-muted-foreground",
    },
    {
      label: "Workers",
      value: `${onlineCount} / ${totalWorkers}`,
      loading: celeryLoading,
      icon: Users,
      color: onlineCount > 0 ? "text-green-500" : "text-muted-foreground",
    },
    {
      label: "ETA",
      value: formatEta(maxEta),
      loading: importsLoading,
      icon: Clock,
      color: "text-muted-foreground",
    },
  ];

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
      {stats.map((stat) => (
        <Card key={stat.label}>
          <CardContent className="flex items-center gap-3 pt-4 pb-3">
            <stat.icon className={`h-5 w-5 shrink-0 ${stat.color}`} />
            <div className="min-w-0">
              {stat.loading ? (
                <Skeleton className="h-6 w-12" />
              ) : (
                <p className="text-xl font-semibold tabular-nums tracking-tight">
                  {stat.value}
                </p>
              )}
              <p className="text-[11px] text-muted-foreground">{stat.label}</p>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
