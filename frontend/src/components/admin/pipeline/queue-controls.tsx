import { useEffect, useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Pause, Play } from "lucide-react";
import { apiClient } from "@/api/client";
import { useNotifications } from "@/hooks/use-notifications";
import { useLiveRefresh } from "@/hooks/use-live-refresh";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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
import { Skeleton } from "@/components/ui/skeleton";
import { CeleryPanel } from "@/components/admin/operations/celery-panel";

interface QueueInfo {
  name: string;
  active: number;
  reserved_count: number;
  scheduled_count: number;
  pending_count: number;
  paused: boolean;
}

interface CeleryOverview {
  queues: QueueInfo[];
}

const KNOWN_QUEUES = ["default", "bulk", "ner", "background"];

export function QueueControls() {
  const notify = useNotifications();
  const { isLive } = useLiveRefresh();
  const queryClient = useQueryClient();
  const [pausedQueues, setPausedQueues] = useState<Set<string>>(new Set());
  const [confirmQueue, setConfirmQueue] = useState<string | null>(null);
  const lastMutationAt = useRef(0);

  const { data, isLoading } = useQuery({
    queryKey: ["admin-celery"],
    queryFn: () =>
      apiClient<CeleryOverview>({
        url: "/api/v1/admin/operations/celery",
        method: "GET",
      }),
    refetchInterval: isLive ? 10_000 : false,
  });

  // Sync pause state from backend on load/refresh, but skip briefly
  // after a mutation so optimistic updates aren't overwritten before
  // Celery's inspect reflects the cancel_consumer/add_consumer change.
  useEffect(() => {
    if (data?.queues && Date.now() - lastMutationAt.current > 3000) {
      setPausedQueues(new Set(data.queues.filter((q) => q.paused).map((q) => q.name)));
    }
  }, [data]);

  const pauseMutation = useMutation({
    mutationFn: (queueName: string) =>
      apiClient({
        url: `/api/v1/admin/queues/${encodeURIComponent(queueName)}/pause`,
        method: "POST",
      }),
    onSuccess: (_, queueName) => {
      lastMutationAt.current = Date.now();
      setPausedQueues((prev) => new Set([...prev, queueName]));
      notify.success(`Queue "${queueName}" paused.`);
      void queryClient.invalidateQueries({ queryKey: ["admin-celery"] });
    },
    onError: (err) => {
      notify.error(err instanceof Error ? err.message : "Failed to pause queue");
    },
  });

  const resumeMutation = useMutation({
    mutationFn: (queueName: string) =>
      apiClient({
        url: `/api/v1/admin/queues/${encodeURIComponent(queueName)}/resume`,
        method: "POST",
      }),
    onSuccess: (_, queueName) => {
      lastMutationAt.current = Date.now();
      setPausedQueues((prev) => {
        const next = new Set(prev);
        next.delete(queueName);
        return next;
      });
      notify.success(`Queue "${queueName}" resumed.`);
      void queryClient.invalidateQueries({ queryKey: ["admin-celery"] });
    },
    onError: (err) => {
      notify.error(err instanceof Error ? err.message : "Failed to resume queue");
    },
  });

  function handlePauseClick(queueName: string) {
    if (pausedQueues.has(queueName)) {
      resumeMutation.mutate(queueName);
    } else {
      setConfirmQueue(queueName);
    }
  }

  function confirmPause() {
    if (!confirmQueue) return;
    pauseMutation.mutate(confirmQueue);
    setConfirmQueue(null);
  }

  const queues = data?.queues ?? [];
  const queueMap = new Map(queues.map((q) => [q.name, q]));

  return (
    <div className="space-y-6">
      {/* Queue pause/resume controls */}
      <div>
        <h3 className="mb-3 text-sm font-semibold">Queue Controls</h3>
        {isLoading ? (
          <div className="grid gap-3 sm:grid-cols-4">
            {KNOWN_QUEUES.map((q) => (
              <Skeleton key={q} className="h-20 w-full" />
            ))}
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-4">
            {KNOWN_QUEUES.map((name) => {
              const info = queueMap.get(name);
              const depth = info
                ? info.pending_count + info.reserved_count + info.scheduled_count
                : 0;
              const isPaused = pausedQueues.has(name);
              return (
                <Card key={name}>
                  <CardContent className="pt-4">
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium font-mono">{name}</span>
                        {isPaused && (
                          <Badge variant="secondary" className="text-[10px] px-1.5 py-0 bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200">
                            Paused
                          </Badge>
                        )}
                      </div>
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-7 text-xs"
                        disabled={pauseMutation.isPending || resumeMutation.isPending}
                        onClick={() => handlePauseClick(name)}
                      >
                        {isPaused ? (
                          <>
                            <Play className="mr-1 h-3 w-3" />
                            Resume
                          </>
                        ) : (
                          <>
                            <Pause className="mr-1 h-3 w-3" />
                            Pause
                          </>
                        )}
                      </Button>
                    </div>
                    <p className="text-lg font-semibold tabular-nums">{depth}</p>
                    <p className="text-[10px] text-muted-foreground">queued tasks</p>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        )}
      </div>

      {/* Reuse CeleryPanel */}
      <CeleryPanel />

      {/* Pause confirmation dialog */}
      <AlertDialog open={!!confirmQueue} onOpenChange={() => setConfirmQueue(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Pause Queue</AlertDialogTitle>
            <AlertDialogDescription>
              Workers will stop pulling new tasks from the &quot;{confirmQueue}&quot; queue.
              Already-running tasks are not affected. You can resume at any time.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={confirmPause}>Pause</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
