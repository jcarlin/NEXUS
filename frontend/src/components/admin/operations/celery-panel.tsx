import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, RotateCcw, Power, Trash2, XCircle } from "lucide-react";
import { apiClient } from "@/api/client";
import { useNotifications } from "@/hooks/use-notifications";
import { cn } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
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

// --- Types ---

interface CeleryWorker {
  hostname: string;
  status: string;
  concurrency: number;
  active_tasks: number;
  processed: number;
  queues: string[];
  uptime_seconds: number;
}

interface ActiveTask {
  task_id: string;
  name: string;
  worker: string;
  queue: string;
  started_at: string;
  runtime_seconds: number;
}

interface QueueInfo {
  name: string;
  active: number;
  reserved: number;
  scheduled: number;
}

interface CeleryOverview {
  workers: CeleryWorker[];
  active_tasks: ActiveTask[];
  queues: QueueInfo[];
}

// --- Helpers ---

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

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}m ${secs}s`;
}

const WORKER_STATUS_STYLES: Record<string, string> = {
  online:
    "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
  offline: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
};

// --- Component ---

export function CeleryPanel() {
  const notify = useNotifications();
  const queryClient = useQueryClient();
  const [confirmAction, setConfirmAction] = useState<{
    type: "shutdown" | "purge";
    target: string;
    label: string;
  } | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["admin-celery"],
    queryFn: () =>
      apiClient<CeleryOverview>({
        url: "/api/v1/admin/operations/celery",
        method: "GET",
      }),
    refetchInterval: 10_000,
  });

  const poolRestartMutation = useMutation({
    mutationFn: (hostname: string) =>
      apiClient<void>({
        url: `/api/v1/admin/operations/celery/workers/${encodeURIComponent(hostname)}/restart`,
        method: "POST",
      }),
    onSuccess: (_, hostname) => {
      notify.success(`Pool restart sent to ${hostname}.`);
      queryClient.invalidateQueries({ queryKey: ["admin-celery"] });
    },
    onError: (err) => {
      notify.error(
        err instanceof Error ? err.message : "Failed to restart pool",
      );
    },
  });

  const shutdownMutation = useMutation({
    mutationFn: (hostname: string) =>
      apiClient<void>({
        url: `/api/v1/admin/operations/celery/workers/${encodeURIComponent(hostname)}/shutdown`,
        method: "POST",
      }),
    onSuccess: (_, hostname) => {
      notify.success(`Shutdown signal sent to ${hostname}.`);
      queryClient.invalidateQueries({ queryKey: ["admin-celery"] });
    },
    onError: (err) => {
      notify.error(
        err instanceof Error ? err.message : "Failed to shutdown worker",
      );
    },
  });

  const purgeMutation = useMutation({
    mutationFn: (queueName: string) =>
      apiClient<void>({
        url: `/api/v1/admin/operations/celery/queues/${encodeURIComponent(queueName)}/purge`,
        method: "POST",
      }),
    onSuccess: (_, queueName) => {
      notify.success(`Purged queue: ${queueName}.`);
      queryClient.invalidateQueries({ queryKey: ["admin-celery"] });
    },
    onError: (err) => {
      notify.error(
        err instanceof Error ? err.message : "Failed to purge queue",
      );
    },
  });

  const revokeMutation = useMutation({
    mutationFn: (taskId: string) =>
      apiClient<void>({
        url: `/api/v1/admin/operations/celery/tasks/${taskId}/revoke`,
        method: "POST",
      }),
    onSuccess: (_, taskId) => {
      notify.success(`Revoked task ${taskId.slice(0, 8)}...`);
      queryClient.invalidateQueries({ queryKey: ["admin-celery"] });
    },
    onError: (err) => {
      notify.error(
        err instanceof Error ? err.message : "Failed to revoke task",
      );
    },
  });

  function handleConfirm() {
    if (!confirmAction) return;
    if (confirmAction.type === "shutdown") {
      shutdownMutation.mutate(confirmAction.target);
    } else if (confirmAction.type === "purge") {
      purgeMutation.mutate(confirmAction.target);
    }
    setConfirmAction(null);
  }

  if (isLoading)
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading Celery status...
      </div>
    );

  const workers = data?.workers ?? [];
  const activeTasks = data?.active_tasks ?? [];
  const queues = data?.queues ?? [];

  return (
    <div className="space-y-6">
      {/* Workers */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Workers</CardTitle>
        </CardHeader>
        <CardContent>
          {workers.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No Celery workers detected.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Hostname</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Concurrency</TableHead>
                  <TableHead className="text-right">Active</TableHead>
                  <TableHead className="text-right">Processed</TableHead>
                  <TableHead>Queues</TableHead>
                  <TableHead>Uptime</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {workers.map((w) => (
                  <TableRow key={w.hostname}>
                    <TableCell className="font-mono text-xs">
                      {w.hostname}
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant="secondary"
                        className={cn(
                          "text-[10px] px-1.5 py-0",
                          WORKER_STATUS_STYLES[w.status] ?? "",
                        )}
                      >
                        {w.status}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      {w.concurrency}
                    </TableCell>
                    <TableCell className="text-right">
                      {w.active_tasks}
                    </TableCell>
                    <TableCell className="text-right">
                      {w.processed.toLocaleString()}
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-1">
                        {w.queues.map((q) => (
                          <span
                            key={q}
                            className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-mono text-muted-foreground"
                          >
                            {q}
                          </span>
                        ))}
                      </div>
                    </TableCell>
                    <TableCell className="text-xs">
                      {formatUptime(w.uptime_seconds)}
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex items-center justify-end gap-1">
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-7 text-xs"
                          disabled={poolRestartMutation.isPending}
                          onClick={() => poolRestartMutation.mutate(w.hostname)}
                        >
                          <RotateCcw className="mr-1 h-3 w-3" />
                          Pool Restart
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-7 text-xs text-destructive hover:text-destructive"
                          disabled={shutdownMutation.isPending}
                          onClick={() =>
                            setConfirmAction({
                              type: "shutdown",
                              target: w.hostname,
                              label: w.hostname,
                            })
                          }
                        >
                          <Power className="mr-1 h-3 w-3" />
                          Shutdown
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Active Tasks */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Active Tasks</CardTitle>
        </CardHeader>
        <CardContent>
          {activeTasks.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No active tasks running.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Task</TableHead>
                  <TableHead>Worker</TableHead>
                  <TableHead>Queue</TableHead>
                  <TableHead className="text-right">Duration</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {activeTasks.map((t) => (
                  <TableRow key={t.task_id}>
                    <TableCell className="font-mono text-xs">
                      {t.name}
                    </TableCell>
                    <TableCell className="text-xs">{t.worker}</TableCell>
                    <TableCell>
                      <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-mono text-muted-foreground">
                        {t.queue}
                      </span>
                    </TableCell>
                    <TableCell className="text-right text-xs">
                      {formatDuration(t.runtime_seconds)}
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-7 text-xs text-destructive hover:text-destructive"
                        disabled={revokeMutation.isPending}
                        onClick={() => revokeMutation.mutate(t.task_id)}
                      >
                        <XCircle className="mr-1 h-3 w-3" />
                        Revoke
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Queues */}
      <div>
        <h3 className="mb-3 text-sm font-semibold">Queues</h3>
        {queues.length === 0 ? (
          <p className="text-sm text-muted-foreground">No queues found.</p>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {queues.map((q) => (
              <Card key={q.name}>
                <CardContent className="pt-4">
                  <div className="flex items-center justify-between mb-3">
                    <span className="text-sm font-medium font-mono">
                      {q.name}
                    </span>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-7 text-xs text-destructive hover:text-destructive"
                      disabled={purgeMutation.isPending}
                      onClick={() =>
                        setConfirmAction({
                          type: "purge",
                          target: q.name,
                          label: q.name,
                        })
                      }
                    >
                      <Trash2 className="mr-1 h-3 w-3" />
                      Purge
                    </Button>
                  </div>
                  <div className="grid grid-cols-3 gap-2 text-center">
                    <div>
                      <p className="text-lg font-semibold">{q.active}</p>
                      <p className="text-[10px] text-muted-foreground">
                        Active
                      </p>
                    </div>
                    <div>
                      <p className="text-lg font-semibold">{q.reserved}</p>
                      <p className="text-[10px] text-muted-foreground">
                        Reserved
                      </p>
                    </div>
                    <div>
                      <p className="text-lg font-semibold">{q.scheduled}</p>
                      <p className="text-[10px] text-muted-foreground">
                        Scheduled
                      </p>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>

      {/* Confirmation dialog */}
      <AlertDialog
        open={!!confirmAction}
        onOpenChange={() => setConfirmAction(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {confirmAction?.type === "shutdown"
                ? "Shutdown Worker"
                : "Purge Queue"}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {confirmAction?.type === "shutdown"
                ? `This will send a shutdown signal to worker "${confirmAction.label}". The worker will stop after completing active tasks.`
                : `This will purge all pending messages from the "${confirmAction?.label}" queue. Active tasks will not be affected.`}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleConfirm}>
              {confirmAction?.type === "shutdown" ? "Shutdown" : "Purge"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
