import { useState } from "react";
import { RotateCcw, Square, Play, ScrollText } from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
import { useNotifications } from "@/hooks/use-notifications";
import { cn } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { LogViewerDialog } from "./log-viewer";

interface ContainerStats {
  cpu_percent: number;
  memory_usage_mb: number;
  memory_limit_mb: number;
  memory_percent: number;
}

export interface ContainerInfo {
  container_id: string;
  name: string;
  service_name: string;
  image: string;
  status: string;
  health: string;
  uptime_seconds: number;
  started_at: string | null;
  stats: ContainerStats | null;
  ports: string[];
}

const STATUS_STYLES: Record<string, string> = {
  running:
    "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
  stopped: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
  exited: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
  dead: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
  restarting:
    "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200",
  paused:
    "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200",
  created:
    "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200",
};

const HEALTH_STYLES: Record<string, string> = {
  healthy:
    "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
  unhealthy: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
  starting:
    "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200",
};

function formatUptime(seconds: number): string {
  if (seconds <= 0) return "---";
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const parts: string[] = [];
  if (days > 0) parts.push(`${days}d`);
  if (hours > 0) parts.push(`${hours}h`);
  parts.push(`${minutes}m`);
  return parts.join(" ");
}

export function ContainerCard({ container }: { container: ContainerInfo }) {
  const notify = useNotifications();
  const queryClient = useQueryClient();
  const [confirmAction, setConfirmAction] = useState<
    "restart" | "stop" | null
  >(null);
  const [showLogs, setShowLogs] = useState(false);

  const isRunning = container.status === "running";

  const restartMutation = useMutation({
    mutationFn: () =>
      apiClient<void>({
        url: `/api/v1/admin/operations/containers/${container.name}/restart`,
        method: "POST",
      }),
    onSuccess: () => {
      notify.success(`Restarting ${container.service_name}...`);
      queryClient.invalidateQueries({ queryKey: ["admin-containers"] });
    },
    onError: (err) => {
      notify.error(
        err instanceof Error ? err.message : "Failed to restart container",
      );
    },
  });

  const stopMutation = useMutation({
    mutationFn: () =>
      apiClient<void>({
        url: `/api/v1/admin/operations/containers/${container.name}/stop`,
        method: "POST",
      }),
    onSuccess: () => {
      notify.success(`Stopped ${container.service_name}.`);
      queryClient.invalidateQueries({ queryKey: ["admin-containers"] });
    },
    onError: (err) => {
      notify.error(
        err instanceof Error ? err.message : "Failed to stop container",
      );
    },
  });

  const startMutation = useMutation({
    mutationFn: () =>
      apiClient<void>({
        url: `/api/v1/admin/operations/containers/${container.name}/start`,
        method: "POST",
      }),
    onSuccess: () => {
      notify.success(`Starting ${container.service_name}...`);
      queryClient.invalidateQueries({ queryKey: ["admin-containers"] });
    },
    onError: (err) => {
      notify.error(
        err instanceof Error ? err.message : "Failed to start container",
      );
    },
  });

  function handleConfirm() {
    if (confirmAction === "restart") {
      restartMutation.mutate();
    } else if (confirmAction === "stop") {
      stopMutation.mutate();
    }
    setConfirmAction(null);
  }

  const imageTag = container.image.includes(":")
    ? container.image.split(":").pop()
    : "latest";

  const isMutating =
    restartMutation.isPending ||
    stopMutation.isPending ||
    startMutation.isPending;

  return (
    <>
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <CardTitle className="text-sm font-semibold truncate">
                {container.service_name}
              </CardTitle>
              <p className="text-xs text-muted-foreground truncate mt-0.5">
                {imageTag}
              </p>
            </div>
            <div className="flex items-center gap-1.5 shrink-0">
              <Badge
                variant="secondary"
                className={cn(
                  "text-[10px] px-1.5 py-0",
                  STATUS_STYLES[container.status] ?? "",
                )}
              >
                {container.status}
              </Badge>
              {container.health !== "none" && (
                <Badge
                  variant="secondary"
                  className={cn(
                    "text-[10px] px-1.5 py-0",
                    HEALTH_STYLES[container.health] ?? "",
                  )}
                >
                  {container.health}
                </Badge>
              )}
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          {/* Uptime */}
          <div className="text-xs text-muted-foreground">
            Uptime: {formatUptime(container.uptime_seconds)}
          </div>

          {/* CPU */}
          {container.stats && (
            <div className="space-y-2">
              <div className="space-y-1">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-muted-foreground">CPU</span>
                  <span className="font-medium">
                    {container.stats.cpu_percent.toFixed(1)}%
                  </span>
                </div>
                <Progress
                  value={Math.min(container.stats.cpu_percent, 100)}
                  className="h-1.5"
                />
              </div>

              {/* Memory */}
              <div className="space-y-1">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-muted-foreground">Memory</span>
                  <span className="font-medium">
                    {container.stats.memory_usage_mb.toFixed(0)} MB /{" "}
                    {container.stats.memory_limit_mb.toFixed(0)} MB
                  </span>
                </div>
                <Progress
                  value={Math.min(container.stats.memory_percent, 100)}
                  className="h-1.5"
                />
              </div>
            </div>
          )}

          {/* Ports */}
          {container.ports.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {container.ports.map((port) => (
                <span
                  key={port}
                  className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-mono text-muted-foreground"
                >
                  {port}
                </span>
              ))}
            </div>
          )}

          {/* Actions */}
          <div className="flex items-center gap-1.5 pt-1">
            <Button
              size="sm"
              variant="outline"
              className="h-7 text-xs"
              disabled={isMutating}
              onClick={() => setConfirmAction("restart")}
            >
              <RotateCcw className="mr-1 h-3 w-3" />
              Restart
            </Button>
            {isRunning ? (
              <Button
                size="sm"
                variant="outline"
                className="h-7 text-xs"
                disabled={isMutating}
                onClick={() => setConfirmAction("stop")}
              >
                <Square className="mr-1 h-3 w-3" />
                Stop
              </Button>
            ) : (
              <Button
                size="sm"
                variant="outline"
                className="h-7 text-xs"
                disabled={isMutating}
                onClick={() => startMutation.mutate()}
              >
                <Play className="mr-1 h-3 w-3" />
                Start
              </Button>
            )}
            <Button
              size="sm"
              variant="ghost"
              className="h-7 text-xs"
              onClick={() => setShowLogs(true)}
            >
              <ScrollText className="mr-1 h-3 w-3" />
              Logs
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Confirmation dialog */}
      <AlertDialog
        open={!!confirmAction}
        onOpenChange={() => setConfirmAction(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {confirmAction === "restart" ? "Restart" : "Stop"}{" "}
              {container.service_name}?
            </AlertDialogTitle>
            <AlertDialogDescription>
              {confirmAction === "restart"
                ? `This will restart the ${container.service_name} container. The service will be briefly unavailable.`
                : `This will stop the ${container.service_name} container. The service will be unavailable until started again.`}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleConfirm}>
              {confirmAction === "restart" ? "Restart" : "Stop"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Log viewer dialog */}
      <LogViewerDialog
        open={showLogs}
        onOpenChange={setShowLogs}
        containerName={container.name}
        serviceName={container.service_name}
      />
    </>
  );
}
