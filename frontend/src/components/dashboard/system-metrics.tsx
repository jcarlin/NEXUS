import { useQuery } from "@tanstack/react-query";
import { Cpu, MemoryStick, HardDrive, MonitorDot } from "lucide-react";
import { apiClient } from "@/api/client";
import { Card, CardContent } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/stores/auth-store";

interface SystemMetricsData {
  cpu_percent: number;
  memory_used_mb: number;
  memory_total_mb: number;
  memory_percent: number;
  disk_used_gb: number;
  disk_total_gb: number;
  disk_percent: number;
  gpu_name: string | null;
  gpu_utilization_percent: number | null;
  gpu_memory_used_mb: number | null;
  gpu_memory_total_mb: number | null;
  gpu_temperature_c: number | null;
}

function percentColor(value: number): string {
  if (value > 90) return "text-red-500";
  if (value > 70) return "text-amber-500";
  return "text-green-600 dark:text-green-400";
}

function formatMb(mb: number): string {
  if (mb >= 1024) return `${(mb / 1024).toFixed(1)} GB`;
  return `${Math.round(mb)} MB`;
}

export function SystemMetrics() {
  const userRole = useAuthStore((s) => s.user?.role);

  const { data } = useQuery({
    queryKey: ["system-metrics"],
    queryFn: () =>
      apiClient<SystemMetricsData>({
        url: "/api/v1/admin/operations/system-metrics",
        method: "GET",
      }),
    refetchInterval: 30_000,
    enabled: userRole === "admin",
    retry: 1,
  });

  if (userRole !== "admin" || !data) return null;

  const metrics = [
    {
      label: "CPU",
      icon: Cpu,
      percent: data.cpu_percent,
      detail: `${data.cpu_percent.toFixed(0)}%`,
    },
    {
      label: "Memory",
      icon: MemoryStick,
      percent: data.memory_percent,
      detail: `${formatMb(data.memory_used_mb)} / ${formatMb(data.memory_total_mb)}`,
    },
    {
      label: "Disk",
      icon: HardDrive,
      percent: data.disk_percent,
      detail: `${data.disk_used_gb} / ${data.disk_total_gb} GB`,
    },
  ];

  const hasGpu = data.gpu_utilization_percent != null;
  if (hasGpu) {
    const gpuMemPercent =
      data.gpu_memory_total_mb && data.gpu_memory_total_mb > 0
        ? (data.gpu_memory_used_mb! / data.gpu_memory_total_mb) * 100
        : 0;
    metrics.push({
      label: "GPU",
      icon: MonitorDot,
      percent: gpuMemPercent,
      detail: `${formatMb(data.gpu_memory_used_mb!)} / ${formatMb(data.gpu_memory_total_mb!)}`,
    });
  }

  return (
    <Card className="shrink-0">
      <CardContent className="flex items-center gap-5 py-3">
        {metrics.map(({ label, icon: Icon, percent, detail }) => (
          <div key={label} className="flex items-center gap-2 min-w-[110px]">
            <Icon className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
            <div className="flex-1 space-y-0.5">
              <div className="flex items-center justify-between text-xs">
                <span className="text-muted-foreground">{label}</span>
                <span className={cn("font-medium tabular-nums", percentColor(percent))}>
                  {detail}
                </span>
              </div>
              <Progress value={Math.min(percent, 100)} className="h-1" />
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
