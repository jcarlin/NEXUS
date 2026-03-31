import { useQuery } from "@tanstack/react-query";
import { Activity, Cpu, HardDrive, MemoryStick } from "lucide-react";
import { apiClient } from "@/api/client";
import { useLiveRefresh } from "@/hooks/use-live-refresh";
import { Card, CardContent } from "@/components/ui/card";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

interface HealthResponse {
  status: string;
  services: Record<string, string>;
}

interface SystemMetrics {
  cpu_percent: number;
  memory_used_mb: number;
  memory_total_mb: number;
  memory_percent: number;
  disk_used_gb: number;
  disk_total_gb: number;
  disk_percent: number;
}

interface TaskTypeThroughput {
  task_type: string;
  jobs_per_minute: number;
  jobs_last_hour: number;
}

interface Throughput {
  jobs_per_minute: number;
  jobs_last_hour: number;
  avg_duration_seconds: number;
  by_type: TaskTypeThroughput[];
}

const TYPE_LABELS: Record<string, string> = {
  ingestion: "ingest",
  entity_resolution: "ner",
  case_setup: "case",
  analysis_sentiment: "sentiment",
  analysis_matter_scan: "hot-scan",
};

function pctColor(pct: number): string {
  if (pct >= 90) return "text-red-500";
  if (pct >= 70) return "text-amber-500";
  return "text-green-500";
}

const SERVICE_NAMES = ["postgres", "qdrant", "neo4j", "redis", "minio"] as const;

export function PipelineHealthStrip() {
  const { isLive } = useLiveRefresh();

  const { data: health } = useQuery({
    queryKey: ["health"],
    queryFn: () =>
      apiClient<HealthResponse>({ url: "/api/v1/health", method: "GET" }),
    refetchInterval: isLive ? 30_000 : false,
  });

  const { data: metrics } = useQuery({
    queryKey: ["admin-system-metrics"],
    queryFn: () =>
      apiClient<SystemMetrics>({
        url: "/api/v1/admin/operations/system-metrics",
        method: "GET",
      }),
    refetchInterval: isLive ? 30_000 : false,
  });

  const { data: throughput } = useQuery({
    queryKey: ["admin-pipeline-throughput"],
    queryFn: () =>
      apiClient<Throughput>({
        url: "/api/v1/admin/pipeline/throughput",
        method: "GET",
      }),
    refetchInterval: isLive ? 30_000 : false,
  });

  const services = health?.services ?? {};

  return (
    <Card>
      <CardContent className="flex flex-wrap items-center gap-6 py-2.5 px-4 text-xs">
        {/* Services */}
        <TooltipProvider delayDuration={200}>
          <div className="flex items-center gap-2">
            <span className="text-muted-foreground font-medium">Services</span>
            <div className="flex items-center gap-1.5">
              {SERVICE_NAMES.map((svc) => {
                const ok = services[svc] === "ok";
                return (
                  <Tooltip key={svc}>
                    <TooltipTrigger asChild>
                      <span
                        className={`h-2.5 w-2.5 rounded-full ${ok ? "bg-green-500" : services[svc] ? "bg-red-500" : "bg-muted-foreground/40"}`}
                      />
                    </TooltipTrigger>
                    <TooltipContent side="bottom" className="text-xs">
                      {svc}: {services[svc] ?? "unknown"}
                    </TooltipContent>
                  </Tooltip>
                );
              })}
            </div>
          </div>
        </TooltipProvider>

        <div className="h-4 w-px bg-border" />

        {/* System metrics */}
        {metrics && (
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1">
              <Cpu className="h-3 w-3 text-muted-foreground" />
              <span className={pctColor(metrics.cpu_percent)}>
                {Math.round(metrics.cpu_percent)}%
              </span>
            </div>
            <div className="flex items-center gap-1">
              <MemoryStick className="h-3 w-3 text-muted-foreground" />
              <span className={pctColor(metrics.memory_percent)}>
                {Math.round(metrics.memory_percent)}%
              </span>
            </div>
            <div className="flex items-center gap-1">
              <HardDrive className="h-3 w-3 text-muted-foreground" />
              <span className={pctColor(metrics.disk_percent)}>
                {Math.round(metrics.disk_percent)}%
              </span>
            </div>
          </div>
        )}

        <div className="h-4 w-px bg-border" />

        {/* Throughput */}
        <div className="flex items-center gap-1">
          <Activity className="h-3 w-3 text-muted-foreground" />
          <span className="text-muted-foreground">
            {throughput
              ? `${throughput.jobs_per_minute.toLocaleString()} jobs/min`
              : "--"}
          </span>
          {throughput && throughput.avg_duration_seconds > 0 && (
            <span className="text-muted-foreground/60 ml-1">
              (avg {Math.round(throughput.avg_duration_seconds)}s)
            </span>
          )}
          {throughput && throughput.by_type.length > 1 && (
            <span className="text-muted-foreground/50 ml-1">
              {throughput.by_type.map((t) => (
                <span key={t.task_type} className="ml-1.5">
                  {TYPE_LABELS[t.task_type] ?? t.task_type}:{" "}
                  {t.jobs_per_minute.toLocaleString()}
                </span>
              ))}
            </span>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
