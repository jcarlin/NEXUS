import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
import { useLiveRefresh } from "@/hooks/use-live-refresh";
import { formatDateTime } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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

interface PipelineEvent {
  id: string;
  job_id: string | null;
  event_type: string;
  timestamp: string;
  worker: string | null;
  detail: Record<string, unknown>;
  duration_ms: number | null;
  filename: string | null;
}

const EVENT_TYPE_STYLES: Record<string, { variant: "default" | "secondary" | "destructive" | "outline"; className: string }> = {
  TASK_COMPLETED: { variant: "secondary", className: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200" },
  STAGE_COMPLETED: { variant: "secondary", className: "bg-green-100/60 text-green-700 dark:bg-green-900/60 dark:text-green-300" },
  TASK_FAILED: { variant: "destructive", className: "" },
  STAGE_FAILED: { variant: "destructive", className: "opacity-80" },
  TASK_RETRIED: { variant: "secondary", className: "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200" },
  STAGE_STARTED: { variant: "secondary", className: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200" },
  TASK_RECEIVED: { variant: "outline", className: "" },
  WORKER_ONLINE: { variant: "secondary", className: "bg-green-100/40 text-green-600 dark:bg-green-900/40 dark:text-green-400" },
  WORKER_OFFLINE: { variant: "outline", className: "text-muted-foreground" },
};

const EVENT_TYPES = [
  "TASK_RECEIVED",
  "STAGE_STARTED",
  "STAGE_COMPLETED",
  "STAGE_FAILED",
  "TASK_RETRIED",
  "TASK_COMPLETED",
  "TASK_FAILED",
  "WORKER_ONLINE",
  "WORKER_OFFLINE",
] as const;

const PAGE_SIZE = 50;

function formatDuration(ms: number | null): string {
  if (ms == null) return "--";
  if (ms < 1000) return `${ms}ms`;
  const secs = Math.round(ms / 1000);
  if (secs < 60) return `${secs}s`;
  const mins = Math.floor(secs / 60);
  return `${mins}m ${secs % 60}s`;
}

export function EventsTab() {
  const { isLive } = useLiveRefresh();
  const [page, setPage] = useState(0);
  const [eventTypeFilter, setEventTypeFilter] = useState<string | undefined>();
  const [jobSearch, setJobSearch] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["pipeline-events", page, eventTypeFilter],
    queryFn: () => {
      const params: Record<string, string | number> = {
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      };
      if (eventTypeFilter) params.event_type = eventTypeFilter;
      return apiClient<PaginatedResponse<PipelineEvent>>({
        url: "/api/v1/admin/pipeline/events",
        method: "GET",
        params,
      });
    },
    refetchInterval: isLive ? 10_000 : false,
  });

  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.ceil(total / PAGE_SIZE);

  const filteredItems = jobSearch
    ? items.filter(
        (e) =>
          e.filename?.toLowerCase().includes(jobSearch.toLowerCase()) ||
          e.job_id?.toLowerCase().includes(jobSearch.toLowerCase()),
      )
    : items;

  if (isLoading && !data) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 10 }).map((_, i) => (
          <Skeleton key={i} className="h-8 w-full" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <Input
          placeholder="Search by filename or job ID..."
          value={jobSearch}
          onChange={(e) => setJobSearch(e.target.value)}
          className="max-w-xs"
        />
        <div className="flex items-center gap-1 flex-wrap">
          <Button
            size="sm"
            variant={!eventTypeFilter ? "default" : "outline"}
            className="h-7 text-xs"
            onClick={() => {
              setEventTypeFilter(undefined);
              setPage(0);
            }}
          >
            All
          </Button>
          {EVENT_TYPES.map((et) => (
            <Button
              key={et}
              size="sm"
              variant={eventTypeFilter === et ? "default" : "outline"}
              className="h-7 text-[10px]"
              onClick={() => {
                setEventTypeFilter(et);
                setPage(0);
              }}
            >
              {et.replace("_", " ")}
            </Button>
          ))}
        </div>
      </div>

      {/* Table */}
      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="text-xs">Timestamp</TableHead>
              <TableHead className="text-xs">Event</TableHead>
              <TableHead className="text-xs">Job</TableHead>
              <TableHead className="text-xs">Worker</TableHead>
              <TableHead className="text-xs text-right">Duration</TableHead>
              <TableHead className="text-xs">Detail</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filteredItems.length > 0 ? (
              filteredItems.map((event) => {
                const style = EVENT_TYPE_STYLES[event.event_type] ?? { variant: "outline" as const, className: "" };
                return (
                  <TableRow key={event.id}>
                    <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                      {formatDateTime(event.timestamp)}
                    </TableCell>
                    <TableCell>
                      <Badge variant={style.variant} className={`text-[9px] ${style.className}`}>
                        {event.event_type}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-xs max-w-[180px] truncate">
                      {event.filename ?? (event.job_id ? event.job_id.slice(0, 8) : "--")}
                    </TableCell>
                    <TableCell className="text-xs font-mono text-muted-foreground">
                      {event.worker ?? "--"}
                    </TableCell>
                    <TableCell className="text-xs text-right tabular-nums text-muted-foreground">
                      {formatDuration(event.duration_ms)}
                    </TableCell>
                    <TableCell className="text-[10px] font-mono text-muted-foreground max-w-[200px] truncate">
                      {Object.keys(event.detail).length > 0
                        ? JSON.stringify(event.detail)
                        : "--"}
                    </TableCell>
                  </TableRow>
                );
              })
            ) : (
              <TableRow>
                <TableCell colSpan={6} className="h-24 text-center text-muted-foreground">
                  No events recorded yet. Events are captured when pipeline tasks run.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between">
        <p className="text-xs text-muted-foreground">
          {total > 0 ? `${total.toLocaleString()} total events` : ""}
        </p>
        {totalPages > 1 && (
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="outline"
              disabled={page === 0}
              onClick={() => setPage((p) => p - 1)}
            >
              Previous
            </Button>
            <span className="text-xs text-muted-foreground">
              Page {page + 1} of {totalPages}
            </span>
            <Button
              size="sm"
              variant="outline"
              disabled={page >= totalPages - 1}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
