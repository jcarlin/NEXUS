import { Fragment, useState } from "react";
import {
  useReactTable,
  getCoreRowModel,
  getExpandedRowModel,
  flexRender,
  createColumnHelper,
} from "@tanstack/react-table";
import { useQuery } from "@tanstack/react-query";
import { ChevronRight, ChevronDown } from "lucide-react";
import { apiClient } from "@/api/client";
import { useAppStore } from "@/stores/app-store";
import { useLiveRefresh } from "@/hooks/use-live-refresh";
import { formatDateTime } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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
import { DataTableColumnHeader } from "@/components/ui/data-table-column-header";
import type { PaginatedResponse } from "@/types";

interface BulkImport {
  import_id: string;
  status: string;
  adapter_type: string | null;
  total_documents: number | null;
  processed_documents: number;
  failed_documents: number;
  skipped_documents: number;
  elapsed_seconds: number | null;
  estimated_remaining_seconds: number | null;
  error: string | null;
  source_path: string | null;
  created_at: string;
  updated_at: string;
}

const PAGE_SIZE = 20;

function statusBadgeProps(status: string): { variant: "default" | "secondary" | "destructive" | "outline"; className: string } {
  switch (status) {
    case "complete":
    case "completed":
      return { variant: "secondary", className: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200" };
    case "processing":
      return { variant: "secondary", className: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200" };
    case "pending":
      return { variant: "secondary", className: "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200" };
    case "failed":
      return { variant: "destructive", className: "" };
    default:
      return { variant: "outline", className: "" };
  }
}

function formatDuration(seconds: number | null): string {
  if (seconds == null || seconds <= 0) return "--";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const mins = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  if (mins < 60) return `${mins}m ${secs}s`;
  const hours = Math.floor(mins / 60);
  const remMins = mins % 60;
  return remMins > 0 ? `${hours}h ${remMins}m` : `${hours}h`;
}

const columnHelper = createColumnHelper<BulkImport>();

const columns = [
  columnHelper.display({
    id: "expand",
    header: () => null,
    cell: ({ row }) => (
      <button
        onClick={(e) => { e.stopPropagation(); row.toggleExpanded(); }}
        className="p-1 hover:bg-muted rounded"
      >
        {row.getIsExpanded() ? (
          <ChevronDown className="h-4 w-4 text-muted-foreground" />
        ) : (
          <ChevronRight className="h-4 w-4 text-muted-foreground" />
        )}
      </button>
    ),
    size: 32,
  }),
  columnHelper.accessor("adapter_type", {
    header: ({ column }) => <DataTableColumnHeader column={column} title="Source" />,
    cell: (info) => {
      const row = info.row.original;
      const pathSegment = row.source_path?.split("/").filter(Boolean).pop();
      return (
        <div className="flex flex-col gap-0.5">
          <Badge variant="outline" className="font-mono text-[10px] w-fit">
            {row.adapter_type ?? "unknown"}
          </Badge>
          {pathSegment && (
            <span className="text-[10px] text-muted-foreground truncate max-w-[200px]" title={row.source_path ?? ""}>
              {pathSegment}
            </span>
          )}
        </div>
      );
    },
  }),
  columnHelper.accessor("status", {
    header: ({ column }) => <DataTableColumnHeader column={column} title="Status" />,
    cell: (info) => {
      const { variant, className } = statusBadgeProps(info.getValue());
      return (
        <Badge variant={variant} className={`text-[10px] ${className}`}>
          {info.getValue()}
        </Badge>
      );
    },
  }),
  columnHelper.display({
    id: "progress",
    header: "Progress",
    cell: ({ row }) => {
      const item = row.original;
      const total = item.total_documents ?? 0;
      const processed = item.processed_documents;
      const pct = total > 0 ? Math.round((processed / total) * 100) : 0;
      return (
        <div className="flex items-center gap-2 min-w-[140px]">
          <Progress value={pct} className="h-1.5 w-20" />
          <span className="text-xs text-muted-foreground whitespace-nowrap">
            {processed.toLocaleString()} / {total.toLocaleString()}
          </span>
        </div>
      );
    },
  }),
  columnHelper.accessor("skipped_documents", {
    header: "Skipped",
    cell: (info) => (
      <span className="text-xs text-muted-foreground">{info.getValue()}</span>
    ),
  }),
  columnHelper.accessor("failed_documents", {
    header: "Failed",
    cell: (info) => {
      const val = info.getValue();
      return (
        <span className={`text-xs ${val > 0 ? "text-destructive font-medium" : "text-muted-foreground"}`}>
          {val}
        </span>
      );
    },
  }),
  columnHelper.accessor("elapsed_seconds", {
    header: "Elapsed",
    cell: (info) => (
      <span className="text-xs text-muted-foreground whitespace-nowrap">
        {formatDuration(info.getValue())}
      </span>
    ),
  }),
  columnHelper.accessor("estimated_remaining_seconds", {
    header: "ETA",
    cell: (info) => (
      <span className="text-xs text-muted-foreground whitespace-nowrap">
        {formatDuration(info.getValue())}
      </span>
    ),
  }),
  columnHelper.accessor("created_at", {
    header: ({ column }) => <DataTableColumnHeader column={column} title="Created" />,
    cell: (info) => (
      <span className="whitespace-nowrap text-xs text-muted-foreground">
        {formatDateTime(info.getValue())}
      </span>
    ),
  }),
];

function BulkImportDetailRow({ importId, importStatus }: { importId: string; importStatus: string }) {
  const matterId = useAppStore((s) => s.matterId);
  const { isLive } = useLiveRefresh();
  const [page, setPage] = useState(0);
  const PAGE = 20;

  const { data, isLoading } = useQuery({
    queryKey: ["bulk-import-jobs", matterId, importId, page],
    queryFn: () =>
      apiClient<PaginatedResponse<{ job_id: string; status: string; stage: string; filename: string | null; progress: { pages_parsed?: number; chunks_created?: number; entities_extracted?: number; embeddings_generated?: number } | null; error: string | null; created_at: string; updated_at: string }>>({
        url: `/api/v1/bulk-imports/${importId}/jobs`,
        method: "GET",
        params: { limit: PAGE, offset: page * PAGE },
      }),
    enabled: !!matterId,
    refetchInterval: isLive && importStatus === "processing" ? 5000 : false,
  });

  if (isLoading) {
    return (
      <div className="bg-muted/30 p-4 space-y-2">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-8 w-full" />
        ))}
      </div>
    );
  }

  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.ceil(total / PAGE);

  if (total === 0) {
    return (
      <div className="bg-muted/30 px-6 py-4 text-sm text-muted-foreground">
        Job tracking was added after this import. Per-document status is not available.
      </div>
    );
  }

  return (
    <div className="bg-muted/30">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b text-muted-foreground">
            <th className="px-4 py-2 text-left font-medium">Filename</th>
            <th className="px-4 py-2 text-left font-medium">Status</th>
            <th className="px-4 py-2 text-left font-medium">Stage</th>
            <th className="px-4 py-2 text-left font-medium">Progress</th>
            <th className="px-4 py-2 text-left font-medium">Error</th>
          </tr>
        </thead>
        <tbody>
          {items.map((job) => (
            <tr key={job.job_id} className="border-b border-border/50">
              <td className="px-4 py-1.5 font-mono truncate max-w-[200px]" title={job.filename ?? ""}>
                {job.filename ?? "--"}
              </td>
              <td className="px-4 py-1.5">
                <Badge {...statusBadgeProps(job.status)} className={`text-[10px] ${statusBadgeProps(job.status).className}`}>
                  {job.status}
                </Badge>
              </td>
              <td className="px-4 py-1.5 text-muted-foreground">{job.stage ?? "--"}</td>
              <td className="px-4 py-1.5 text-muted-foreground">
                {job.progress
                  ? `${job.progress.chunks_created ?? 0} chunks`
                  : "--"}
              </td>
              <td className="px-4 py-1.5 text-destructive truncate max-w-[200px]" title={job.error ?? ""}>
                {job.error ?? ""}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {totalPages > 1 && (
        <div className="flex items-center justify-between px-4 py-2 border-t">
          <span className="text-xs text-muted-foreground">{total} jobs</span>
          <div className="flex items-center gap-2">
            <Button size="sm" variant="ghost" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>
              Prev
            </Button>
            <span className="text-xs text-muted-foreground">{page + 1} / {totalPages}</span>
            <Button size="sm" variant="ghost" disabled={page >= totalPages - 1} onClick={() => setPage((p) => p + 1)}>
              Next
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

export function BulkImportTable() {
  const matterId = useAppStore((s) => s.matterId);
  const { isLive } = useLiveRefresh();
  const [page, setPage] = useState(0);

  const { data, isLoading } = useQuery({
    queryKey: ["pipeline-bulk-imports", matterId, page],
    queryFn: () =>
      apiClient<PaginatedResponse<BulkImport>>({
        url: "/api/v1/bulk-imports",
        method: "GET",
        params: { limit: PAGE_SIZE, offset: page * PAGE_SIZE },
      }),
    enabled: !!matterId,
    refetchInterval: !isLive
      ? false
      : (query) => {
          const d = query.state.data;
          if (!d) return 10000;
          const hasActive = d.items.some((i) => i.status === "processing");
          return hasActive ? 5000 : false;
        },
  });

  const table = useReactTable({
    data: data?.items ?? [],
    columns,
    getCoreRowModel: getCoreRowModel(),
    getExpandedRowModel: getExpandedRowModel(),
    getRowCanExpand: () => true,
  });

  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 0;

  if (isLoading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-10 w-full" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-4">
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
                <Fragment key={row.id}>
                  <TableRow onClick={() => row.toggleExpanded()} className="cursor-pointer">
                    {row.getVisibleCells().map((cell) => (
                      <TableCell key={cell.id}>
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </TableCell>
                    ))}
                  </TableRow>
                  {row.getIsExpanded() && (
                    <TableRow key={`${row.id}-detail`}>
                      <TableCell colSpan={row.getVisibleCells().length} className="p-0">
                        <BulkImportDetailRow importId={row.original.import_id} importStatus={row.original.status} />
                      </TableCell>
                    </TableRow>
                  )}
                </Fragment>
              ))
            ) : (
              <TableRow>
                <TableCell colSpan={columns.length} className="h-24 text-center">
                  No bulk imports found.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between">
        <p className="text-xs text-muted-foreground">
          {data ? `${data.total.toLocaleString()} total imports` : ""}
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
