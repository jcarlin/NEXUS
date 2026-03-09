import { useMemo, useState } from "react";
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getFilteredRowModel,
  flexRender,
  type ColumnDef,
  type SortingState,
} from "@tanstack/react-table";
import { Download } from "lucide-react";
import { apiFetchRaw } from "@/api/client";
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
import { Skeleton } from "@/components/ui/skeleton";
import { Pagination } from "@/components/ui/pagination";
import { DataTableColumnHeader } from "@/components/ui/data-table-column-header";
import { DataTableToolbar } from "@/components/ui/data-table-toolbar";
import type { ExportJob } from "@/routes/review/exports";

interface Props {
  data: ExportJob[];
  loading: boolean;
  total: number;
  offset: number;
  limit: number;
  onOffsetChange: (offset: number) => void;
}

const statusColors: Record<string, string> = {
  pending: "bg-yellow-500/15 text-yellow-700",
  processing: "bg-blue-500/15 text-blue-700",
  complete: "bg-green-500/15 text-green-700",
  failed: "bg-red-500/15 text-red-700",
};

function DownloadButton({ jobId }: { jobId: string }) {
  const handleDownload = async () => {
    const res = await apiFetchRaw(`/api/v1/exports/jobs/${jobId}/download`);
    const blob = await res.blob();
    const filename =
      res.headers.get("content-disposition")?.match(/filename="(.+)"/)?.[1] ?? "export";
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

  return (
    <Button variant="outline" size="sm" onClick={handleDownload}>
      <Download className="mr-1.5 h-3.5 w-3.5" />
      Download
    </Button>
  );
}

export function ExportJobList({
  data,
  loading,
  total,
  offset,
  limit,
  onOffsetChange,
}: Props) {
  const [sorting, setSorting] = useState<SortingState>([]);
  const [globalFilter, setGlobalFilter] = useState("");

  const columns = useMemo<ColumnDef<ExportJob>[]>(
    () => [
      {
        accessorKey: "export_type",
        header: ({ column }) => <DataTableColumnHeader column={column} title="Type" />,
        cell: ({ row }) => <span className="font-medium">{row.original.export_type}</span>,
      },
      {
        accessorKey: "export_format",
        header: ({ column }) => <DataTableColumnHeader column={column} title="Format" />,
      },
      {
        accessorKey: "status",
        header: ({ column }) => <DataTableColumnHeader column={column} title="Status" />,
        cell: ({ row }) => (
          <Badge variant="secondary" className={statusColors[row.original.status] ?? ""}>
            {row.original.status}
          </Badge>
        ),
      },
      {
        accessorKey: "created_at",
        header: ({ column }) => <DataTableColumnHeader column={column} title="Created" />,
        cell: ({ row }) => (
          <span className="text-muted-foreground text-xs">
            {new Date(row.original.created_at).toLocaleDateString()}
          </span>
        ),
      },
      {
        accessorKey: "completed_at",
        header: ({ column }) => <DataTableColumnHeader column={column} title="Completed" />,
        cell: ({ row }) => (
          <span className="text-muted-foreground text-xs">
            {row.original.completed_at
              ? new Date(row.original.completed_at).toLocaleDateString()
              : "\u2014"}
          </span>
        ),
      },
      {
        id: "actions",
        cell: ({ row }) => {
          if (row.original.status === "complete") return <DownloadButton jobId={row.original.id} />;
          if (row.original.status === "failed" && row.original.error) {
            return (
              <span className="text-xs text-destructive truncate max-w-[200px] block">
                {row.original.error}
              </span>
            );
          }
          return null;
        },
        enableSorting: false,
        enableGlobalFilter: false,
      },
    ],
    [],
  );

  const table = useReactTable({
    data,
    columns,
    state: { sorting, globalFilter },
    onSortingChange: setSorting,
    onGlobalFilterChange: setGlobalFilter,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
  });

  if (loading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <DataTableToolbar table={table} searchPlaceholder="Search export jobs..." />

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
                <TableCell colSpan={columns.length} className="text-center text-muted-foreground py-8">
                  No export jobs yet. Create one to get started.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      {total > limit && (
        <Pagination
          total={total}
          offset={offset}
          limit={limit}
          onOffsetChange={onOffsetChange}
        />
      )}
    </div>
  );
}
