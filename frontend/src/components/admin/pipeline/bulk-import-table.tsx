import { useState } from "react";
import {
  useReactTable,
  getCoreRowModel,
  flexRender,
  createColumnHelper,
} from "@tanstack/react-table";
import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
import { useAppStore } from "@/stores/app-store";
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
  created_at: string;
  updated_at: string;
}

const PAGE_SIZE = 20;

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
  columnHelper.accessor("adapter_type", {
    header: ({ column }) => <DataTableColumnHeader column={column} title="Source" />,
    cell: (info) => (
      <Badge variant="outline" className="font-mono text-[10px]">
        {info.getValue() ?? "unknown"}
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

export function BulkImportTable() {
  const matterId = useAppStore((s) => s.matterId);
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
    refetchInterval: (query) => {
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
