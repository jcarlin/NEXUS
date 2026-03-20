import { useState } from "react";
import {
  useReactTable,
  getCoreRowModel,
  flexRender,
  createColumnHelper,
} from "@tanstack/react-table";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { RotateCcw, X } from "lucide-react";
import { toast } from "sonner";
import { apiClient } from "@/api/client";
import { useAppStore } from "@/stores/app-store";
import { formatDateTime } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
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

const PAGE_SIZE = 50;

function statusVariant(status: string) {
  switch (status) {
    case "complete":
    case "completed":
      return "default" as const;
    case "failed":
      return "destructive" as const;
    case "processing":
      return "secondary" as const;
    default:
      return "outline" as const;
  }
}

function jobProgress(job: JobStatusResponse): number {
  if (job.status === "complete" || job.status === "completed") return 100;
  if (job.status === "failed") return 0;
  const p = job.progress;
  if (!p) return 0;
  const stages = ["parsing", "chunking", "embedding", "extracting", "indexing", "completed"];
  const idx = stages.indexOf(p.stage);
  return idx >= 0 ? Math.round(((idx + 1) / stages.length) * 100) : 10;
}

const columnHelper = createColumnHelper<JobStatusResponse>();

export function JobTable() {
  const matterId = useAppStore((s) => s.matterId);
  const queryClient = useQueryClient();
  const [page, setPage] = useState(0);
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [search, setSearch] = useState("");

  const params: Record<string, string | number> = {
    limit: PAGE_SIZE,
    offset: page * PAGE_SIZE,
  };
  if (statusFilter !== "all") params.status = statusFilter;

  const { data, isLoading } = useQuery({
    queryKey: ["pipeline-jobs-table", matterId, page, statusFilter],
    queryFn: () =>
      apiClient<PaginatedResponse<JobStatusResponse>>({
        url: "/api/v1/jobs",
        method: "GET",
        params,
      }),
    enabled: !!matterId,
    refetchInterval: (query) => {
      const d = query.state.data;
      if (!d) return 5000;
      const hasActive = d.items.some((j) => j.status === "processing");
      return hasActive ? 5000 : false;
    },
  });

  const cancelMutation = useMutation({
    mutationFn: (jobId: string) =>
      apiClient({ url: `/api/v1/jobs/${jobId}`, method: "DELETE" }),
    onSuccess: () => {
      toast.success("Job cancelled");
      void queryClient.invalidateQueries({ queryKey: ["pipeline-jobs-table"] });
      void queryClient.invalidateQueries({ queryKey: ["pipeline-processing-count"] });
    },
    onError: () => toast.error("Failed to cancel job"),
  });

  const retryMutation = useMutation({
    mutationFn: (jobId: string) =>
      apiClient({ url: `/api/v1/jobs/${jobId}/retry`, method: "POST" }),
    onSuccess: () => {
      toast.success("Job retried");
      void queryClient.invalidateQueries({ queryKey: ["pipeline-jobs-table"] });
      void queryClient.invalidateQueries({ queryKey: ["pipeline-failed-count"] });
    },
    onError: () => toast.error("Failed to retry job"),
  });

  const columns = [
    columnHelper.accessor("filename", {
      header: ({ column }) => <DataTableColumnHeader column={column} title="Filename" />,
      cell: (info) => (
        <span className="text-sm font-medium truncate max-w-[240px] block">
          {info.getValue() ?? info.row.original.job_id.slice(0, 8)}
        </span>
      ),
    }),
    columnHelper.accessor("document_type", {
      header: "Type",
      cell: (info) => (
        <Badge variant="outline" className="font-mono text-[10px]">
          {info.getValue() ?? "ingestion"}
        </Badge>
      ),
    }),
    columnHelper.accessor("status", {
      header: ({ column }) => <DataTableColumnHeader column={column} title="Status" />,
      cell: (info) => (
        <Badge variant={statusVariant(info.getValue())} className="text-[10px]">
          {info.getValue()}
        </Badge>
      ),
    }),
    columnHelper.display({
      id: "stage",
      header: "Stage",
      cell: ({ row }) => {
        const job = row.original;
        if (job.status !== "processing") return <span className="text-xs text-muted-foreground">--</span>;
        return <span className="text-xs">{job.progress?.stage ?? "starting"}</span>;
      },
    }),
    columnHelper.display({
      id: "progress",
      header: "Progress",
      cell: ({ row }) => {
        const job = row.original;
        if (job.status !== "processing") return null;
        return <Progress value={jobProgress(job)} className="h-1.5 w-20" />;
      },
    }),
    columnHelper.accessor("created_at", {
      header: ({ column }) => <DataTableColumnHeader column={column} title="Created" />,
      cell: (info) => (
        <span className="whitespace-nowrap text-xs text-muted-foreground">
          {formatDateTime(info.getValue())}
        </span>
      ),
    }),
    columnHelper.display({
      id: "actions",
      header: "",
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
          );
        }
        return null;
      },
    }),
  ];

  // Client-side filename search on already-fetched page
  const items = (data?.items ?? []).filter((job) => {
    if (!search) return true;
    const term = search.toLowerCase();
    return (
      (job.filename?.toLowerCase().includes(term)) ||
      job.job_id.toLowerCase().includes(term)
    );
  });

  const table = useReactTable({
    data: items,
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 0;

  if (isLoading) {
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
        <Select
          value={statusFilter}
          onValueChange={(v) => {
            setStatusFilter(v);
            setPage(0);
          }}
        >
          <SelectTrigger className="w-[150px]">
            <SelectValue placeholder="All statuses" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
            <SelectItem value="pending">Pending</SelectItem>
            <SelectItem value="processing">Processing</SelectItem>
            <SelectItem value="completed">Completed</SelectItem>
            <SelectItem value="failed">Failed</SelectItem>
          </SelectContent>
        </Select>
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
                      : flexRender(header.column.columnDef.header, header.getContext())}
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
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </TableCell>
                  ))}
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell colSpan={columns.length} className="h-24 text-center">
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
