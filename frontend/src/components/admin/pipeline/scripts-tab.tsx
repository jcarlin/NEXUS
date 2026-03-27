import { useQuery } from "@tanstack/react-query";
import { FileCode2 } from "lucide-react";
import { apiClient } from "@/api/client";
import { useLiveRefresh } from "@/hooks/use-live-refresh";
import { formatDateTime } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { PaginatedResponse } from "@/types";

interface ExternalTask {
  id: string;
  name: string;
  script_name: string;
  status: string;
  total: number;
  processed: number;
  failed: number;
  error: string | null;
  started_at: string;
  updated_at: string;
  completed_at: string | null;
}

function statusBadge(status: string) {
  switch (status) {
    case "running":
      return (
        <Badge variant="secondary" className="text-[10px] bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200">
          running
        </Badge>
      );
    case "complete":
      return (
        <Badge variant="secondary" className="text-[10px] bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200">
          complete
        </Badge>
      );
    case "failed":
      return <Badge variant="destructive" className="text-[10px]">failed</Badge>;
    case "stale":
      return (
        <Badge variant="outline" className="text-[10px] text-amber-600">
          stale
        </Badge>
      );
    default:
      return <Badge variant="outline" className="text-[10px]">{status}</Badge>;
  }
}

export function ScriptsTab() {
  const { isLive } = useLiveRefresh();

  const { data, isLoading } = useQuery({
    queryKey: ["external-tasks"],
    queryFn: () =>
      apiClient<PaginatedResponse<ExternalTask>>({
        url: "/api/v1/scripts/tasks",
        method: "GET",
        params: { limit: 50 },
      }),
    refetchInterval: isLive ? 10_000 : false,
  });

  const items = data?.items ?? [];

  if (isLoading && !data) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-8 w-full" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="text-xs">Name</TableHead>
              <TableHead className="text-xs">Script</TableHead>
              <TableHead className="text-xs">Status</TableHead>
              <TableHead className="text-xs w-40">Progress</TableHead>
              <TableHead className="text-xs text-right">Failed</TableHead>
              <TableHead className="text-xs">Error</TableHead>
              <TableHead className="text-xs">Started</TableHead>
              <TableHead className="text-xs">Last Update</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.length > 0 ? (
              items.map((task) => {
                const pct = task.total > 0 ? Math.round((task.processed / task.total) * 100) : 0;
                return (
                  <TableRow key={task.id}>
                    <TableCell className="text-sm font-medium">
                      {task.name}
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline" className="font-mono text-[10px]">
                        {task.script_name}
                      </Badge>
                    </TableCell>
                    <TableCell>{statusBadge(task.status)}</TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <Progress value={pct} className="h-1.5 flex-1" />
                        <span className="text-[10px] tabular-nums text-muted-foreground w-16 text-right">
                          {task.processed.toLocaleString()}/{task.total.toLocaleString()}
                        </span>
                      </div>
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      <span className={task.failed > 0 ? "text-destructive text-xs" : "text-xs text-muted-foreground"}>
                        {task.failed}
                      </span>
                    </TableCell>
                    <TableCell className="text-[10px] font-mono text-muted-foreground max-w-[200px] truncate" title={task.error ?? ""}>
                      {task.error ?? "--"}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                      {formatDateTime(task.started_at)}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                      {formatDateTime(task.updated_at)}
                    </TableCell>
                  </TableRow>
                );
              })
            ) : (
              <TableRow>
                <TableCell colSpan={8} className="h-32 text-center">
                  <div className="flex flex-col items-center gap-2 text-muted-foreground">
                    <FileCode2 className="h-8 w-8 opacity-40" />
                    <p className="text-sm">No scripts running.</p>
                    <p className="text-xs max-w-md">
                      Use <code className="rounded bg-muted px-1 py-0.5 font-mono text-[11px]">TaskTracker</code>{" "}
                      in your scripts to track progress here.
                      See <code className="rounded bg-muted px-1 py-0.5 font-mono text-[11px]">scripts/lib/task_tracker.py</code>.
                    </p>
                  </div>
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
