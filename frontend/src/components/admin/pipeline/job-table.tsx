import { useMemo, useState } from "react";
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  flexRender,
  createColumnHelper,
  type SortingState,
} from "@tanstack/react-table";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { EyeOff, RotateCcw, X } from "lucide-react";
import { toast } from "sonner";
import { apiClient } from "@/api/client";
import { useAppStore } from "@/stores/app-store";
import { useLiveRefresh } from "@/hooks/use-live-refresh";
import { formatDateTime, formatFileSize } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { DataTableColumnHeader } from "@/components/ui/data-table-column-header";
import type { PaginatedResponse, JobStatusResponse } from "@/types";

const PAGE_SIZE = 25;

const STATUS_OPTIONS = [
  { value: "pending", label: "Pending" },
  { value: "processing", label: "Processing" },
  { value: "complete", label: "Completed" },
  { value: "failed", label: "Failed" },
  { value: "dismissed", label: "Dismissed" },
] as const;

function statusBadgeProps(status: string): {
  variant: "default" | "secondary" | "destructive" | "outline";
  className: string;
} {
  switch (status) {
    case "complete":
    case "completed":
      return {
        variant: "secondary",
        className:
          "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
      };
    case "processing":
      return {
        variant: "secondary",
        className:
          "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200",
      };
    case "pending":
      return {
        variant: "secondary",
        className:
          "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200",
      };
    case "failed":
      return { variant: "destructive", className: "" };
    case "dismissed":
      return { variant: "outline", className: "text-muted-foreground" };
    default:
      return { variant: "outline", className: "" };
  }
}

function jobProgress(job: JobStatusResponse): number {
  if (job.status === "complete" || job.status === "completed") return 100;
  if (job.status === "failed") return 0;
  const p = job.progress;
  if (!p) return 0;
  const stages = [
    "parsing",
    "chunking",
    "embedding",
    "extracting",
    "indexing",
    "completed",
  ];
  const idx = stages.indexOf(p.stage);
  return idx >= 0 ? Math.round(((idx + 1) / stages.length) * 100) : 10;
}

const columnHelper = createColumnHelper<JobStatusResponse>();

export function JobTable() {
  const matterId = useAppStore((s) => s.matterId);
  const { isLive } = useLiveRefresh();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(0);
  const [selectedStatuses, setSelectedStatuses] = useState<Set<string>>(
    new Set(),
  );
  const [search, setSearch] = useState("");
  const [sorting, setSorting] = useState<SortingState>([]);

  const statusParam =
    selectedStatuses.size > 0
      ? Array.from(selectedStatuses).join(",")
      : undefined;

  const params: Record<string, string | number> = {
    limit: PAGE_SIZE,
    offset: page * PAGE_SIZE,
  };
  if (statusParam) params.status = statusParam;

  const { data, isLoading } = useQuery({
    queryKey: ["pipeline-jobs-table", matterId, page, statusParam],
    queryFn: () =>
      apiClient<PaginatedResponse<JobStatusResponse>>({
        url: "/api/v1/jobs",
        method: "GET",
        params,
      }),
    enabled: !!matterId,
    refetchInterval: isLive && !statusParam ? 5_000 : false,
    gcTime: 5 * 60_000,
  });

  const cancelMutation = useMutation({
    mutationFn: (jobId: string) =>
      apiClient({ url: `/api/v1/jobs/${jobId}`, method: "DELETE" }),
    onSuccess: () => {
      toast.success("Job cancelled");
      void queryClient.invalidateQueries({
        queryKey: ["pipeline-jobs-table"],
      });
      void queryClient.invalidateQueries({
        queryKey: ["pipeline-processing-count"],
      });
    },
    onError: () => toast.error("Failed to cancel job"),
  });

  const retryMutation = useMutation({
    mutationFn: (jobId: string) =>
      apiClient({ url: `/api/v1/jobs/${jobId}/retry`, method: "POST" }),
    onSuccess: () => {
      toast.success("Job retried");
      void queryClient.invalidateQueries({
        queryKey: ["pipeline-jobs-table"],
      });
      void queryClient.invalidateQueries({
        queryKey: ["pipeline-failed-count"],
      });
    },
    onError: () => toast.error("Failed to retry job"),
  });

  const dismissMutation = useMutation({
    mutationFn: (jobId: string) =>
      apiClient({ url: `/api/v1/jobs/${jobId}/dismiss`, method: "POST" }),
    onSuccess: () => {
      toast.success("Job dismissed");
      void queryClient.invalidateQueries({
        queryKey: ["pipeline-jobs-table"],
      });
      void queryClient.invalidateQueries({
        queryKey: ["pipeline-failed-count"],
      });
    },
    onError: () => toast.error("Failed to dismiss job"),
  });

  function toggleStatus(value: string) {
    setSelectedStatuses((prev) => {
      const next = new Set(prev);
      if (next.has(value)) next.delete(value);
      else next.add(value);
      return next;
    });
    setPage(0);
  }

  const columns = useMemo(() => [
    columnHelper.accessor("filename", {
      header: ({ column }) => (
        <DataTableColumnHeader column={column} title="Filename" />
      ),
      cell: (info) => (
        <span className="text-sm font-medium truncate max-w-[240px] block">
          {info.getValue() ?? info.row.original.job_id.slice(0, 8)}
        </span>
      ),
    }),
    columnHelper.accessor("document_type", {
      header: ({ column }) => (
        <DataTableColumnHeader column={column} title="Type" />
      ),
      cell: (info) => (
        <Badge variant="outline" className="font-mono text-[10px]">
          {info.getValue() ?? "ingestion"}
        </Badge>
      ),
    }),
    columnHelper.accessor("status", {
      header: ({ column }) => (
        <DataTableColumnHeader column={column} title="Status" />
      ),
      cell: (info) => {
        const { variant, className } = statusBadgeProps(info.getValue());
        return (
          <Badge variant={variant} className={`text-[10px] ${className}`}>
            {info.getValue()}
          </Badge>
        );
      },
    }),
    columnHelper.accessor((row) => row.progress?.stage ?? "", {
      id: "stage",
      header: ({ column }) => (
        <DataTableColumnHeader column={column} title="Stage" />
      ),
      cell: ({ row }) => {
        const job = row.original;
        if (job.status !== "processing")
          return (
            <span className="text-xs text-muted-foreground">--</span>
          );
        return (
          <span className="text-xs">
            {job.progress?.stage ?? "starting"}
          </span>
        );
      },
    }),
    columnHelper.accessor((row) => jobProgress(row), {
      id: "progress",
      header: ({ column }) => (
        <DataTableColumnHeader column={column} title="Progress" />
      ),
      cell: ({ row }) => {
        const job = row.original;
        if (job.status !== "processing") return null;
        return <Progress value={jobProgress(job)} className="h-1.5 w-20" />;
      },
    }),
    columnHelper.accessor("page_count", {
      header: ({ column }) => (
        <DataTableColumnHeader column={column} title="Pages" />
      ),
      cell: (info) => {
        const val = info.getValue();
        return (
          <span className="text-xs text-muted-foreground">
            {val != null ? val.toLocaleString() : "--"}
          </span>
        );
      },
    }),
    columnHelper.accessor("file_size_bytes", {
      header: ({ column }) => (
        <DataTableColumnHeader column={column} title="Size" />
      ),
      cell: (info) => {
        const val = info.getValue();
        return (
          <span className="text-xs text-muted-foreground whitespace-nowrap">
            {val != null ? formatFileSize(val) : "--"}
          </span>
        );
      },
    }),
    columnHelper.accessor("created_at", {
      header: ({ column }) => (
        <DataTableColumnHeader column={column} title="Created" />
      ),
      cell: (info) => (
        <span className="whitespace-nowrap text-xs text-muted-foreground">
          {formatDateTime(info.getValue())}
        </span>
      ),
    }),
    columnHelper.display({
      id: "actions",
      header: "",
      enableSorting: false,
      cell: ({ row }) => {
        const job = row.original;
        if (job.status === "processing") {
          return (
            <Button
              size="sm"
              variant="ghost"
              className="h-7 text-xs text-destructive hover:text-destructive"
              disabled={cancelMutation.isPending}
              onClick={() => cancelMutation.mutate(job.job_id)}
            >
              <X className="mr-1 h-3 w-3" />
              Cancel
            </Button>
          );
        }
        if (job.status === "failed") {
          return (
            <div className="flex gap-1">
              <Button
                size="sm"
                variant="ghost"
                className="h-7 text-xs"
                disabled={retryMutation.isPending}
                onClick={() => retryMutation.mutate(job.job_id)}
              >
                <RotateCcw className="mr-1 h-3 w-3" />
                Retry
              </Button>
              <Button
                size="sm"
                variant="ghost"
                className="h-7 text-xs text-muted-foreground"
                disabled={dismissMutation.isPending}
                onClick={() => dismissMutation.mutate(job.job_id)}
              >
                <EyeOff className="mr-1 h-3 w-3" />
                Dismiss
              </Button>
            </div>
          );
        }
        return null;
      },
    }),
  // eslint-disable-next-line react-hooks/exhaustive-deps
  ], [cancelMutation.isPending, retryMutation.isPending, dismissMutation.isPending]);

  // Client-side filename search on already-fetched page
  const items = (data?.items ?? []).filter((job) => {
    if (!search) return true;
    const term = search.toLowerCase();
    return (
      job.filename?.toLowerCase().includes(term) ||
      job.job_id.toLowerCase().includes(term)
    );
  });

  const table = useReactTable({
    data: items,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 0;

  if (isLoading && !data) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 8 }).map((_, i) => (
          <Skeleton key={i} className="h-10 w-full" />
        ))}
      </div>
    );
  }


  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-3">
        <Input
          placeholder="Search by filename..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-xs"
        />

        {/* Status filter toggle buttons */}
        <div className="flex items-center gap-1">
          {STATUS_OPTIONS.map((opt) => {
            const isSelected = selectedStatuses.has(opt.value);
            return (
              <Button
                key={opt.value}
                size="sm"
                variant={isSelected ? "default" : "outline"}
                className="h-7 text-xs"
                onClick={() => toggleStatus(opt.value)}
              >
                {opt.label}
              </Button>
            );
          })}
          {selectedStatuses.size > 0 && (
            <Button
              size="sm"
              variant="ghost"
              className="h-7 text-xs text-muted-foreground"
              onClick={() => {
                setSelectedStatuses(new Set());
                setPage(0);
              }}
            >
              <X className="mr-1 h-3 w-3" />
              Clear
            </Button>
          )}
        </div>
      </div>

      {/* Table */}
      <div className="rounded-md border">
        <Table>
          <TableHeader>
            {table.getHeaderGroups().map((headerGroup) => (
              <TableRow key={headerGroup.id}>
                {headerGroup.headers.map((header) => (
                  <TableHead key={header.id}>
                    {header.isPlaceholder
                      ? null
                      : flexRender(
                          header.column.columnDef.header,
                          header.getContext(),
                        )}
                  </TableHead>
                ))}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {table.getRowModel().rows.length ? (
              table.getRowModel().rows.map((row) => (
                <TableRow key={row.id}>
                  {row.getVisibleCells().map((cell) => (
                    <TableCell key={cell.id}>
                      {flexRender(
                        cell.column.columnDef.cell,
                        cell.getContext(),
                      )}
                    </TableCell>
                  ))}
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell
                  colSpan={columns.length}
                  className="h-24 text-center"
                >
                  No jobs found.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between">
        <p className="text-xs text-muted-foreground">
          {data ? `${data.total.toLocaleString()} total jobs` : ""}
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
