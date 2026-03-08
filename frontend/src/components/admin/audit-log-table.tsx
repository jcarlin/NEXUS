import { useMemo, useState } from "react";
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getFilteredRowModel,
  flexRender,
  createColumnHelper,
  type SortingState,
} from "@tanstack/react-table";
import { Download } from "lucide-react";
import type { AuditLogEntry } from "@/types";
import { formatDateTime, cn } from "@/lib/utils";
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
import { DataTableColumnHeader } from "@/components/ui/data-table-column-header";
import { DataTableToolbar } from "@/components/ui/data-table-toolbar";

const columnHelper = createColumnHelper<AuditLogEntry>();

function statusColor(code: number): string {
  if (code >= 200 && code < 300) return "text-green-500";
  if (code >= 400 && code < 500) return "text-yellow-500";
  return "text-red-500";
}

const columns = [
  columnHelper.accessor("created_at", {
    header: ({ column }) => <DataTableColumnHeader column={column} title="Timestamp" />,
    cell: (info) => (
      <span className="whitespace-nowrap text-xs">{formatDateTime(info.getValue())}</span>
    ),
  }),
  columnHelper.accessor("user_email", {
    header: ({ column }) => <DataTableColumnHeader column={column} title="User" />,
    cell: (info) => (
      <span className="text-sm">{info.getValue() ?? "anonymous"}</span>
    ),
  }),
  columnHelper.accessor("action", {
    header: ({ column }) => <DataTableColumnHeader column={column} title="Action" />,
    cell: (info) => (
      <Badge variant="outline" className="font-mono text-[10px]">
        {info.getValue()}
      </Badge>
    ),
    filterFn: (row, _columnId, filterValue) => row.original.action === filterValue,
  }),
  columnHelper.accessor("resource", {
    header: ({ column }) => <DataTableColumnHeader column={column} title="Resource" />,
    cell: (info) => (
      <span className="max-w-[200px] truncate text-xs text-muted-foreground">
        {info.getValue()}
      </span>
    ),
  }),
  columnHelper.accessor("status_code", {
    header: ({ column }) => <DataTableColumnHeader column={column} title="Status" />,
    cell: (info) => {
      const code = info.getValue();
      return (
        <span className={cn("font-mono text-sm font-medium", statusColor(code))}>
          {code}
        </span>
      );
    },
  }),
  columnHelper.accessor("ip_address", {
    header: ({ column }) => <DataTableColumnHeader column={column} title="IP" />,
    cell: (info) => (
      <span className="font-mono text-xs text-muted-foreground">{info.getValue()}</span>
    ),
  }),
  columnHelper.accessor("duration_ms", {
    header: ({ column }) => <DataTableColumnHeader column={column} title="Duration" />,
    cell: (info) => {
      const ms = info.getValue();
      return ms != null ? (
        <span className="text-xs text-muted-foreground">{ms}ms</span>
      ) : (
        <span className="text-xs text-muted-foreground">-</span>
      );
    },
  }),
];

interface AuditLogTableProps {
  data: AuditLogEntry[];
  isLoading: boolean;
}

export function AuditLogTable({ data, isLoading }: AuditLogTableProps) {
  const [sorting, setSorting] = useState<SortingState>([]);
  const [globalFilter, setGlobalFilter] = useState("");

  const actionFacetOptions = useMemo(() => {
    const actions = [...new Set(data.map((e) => e.action))].sort();
    return actions.map((a) => ({ label: a, value: a }));
  }, [data]);

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

  function exportCSV() {
    const rows = table.getFilteredRowModel().rows;
    const headers = ["timestamp", "user_email", "action", "resource", "status_code", "ip_address", "duration_ms"];
    const csvRows = [headers.join(",")];
    for (const row of rows) {
      const e = row.original;
      csvRows.push(
        [
          e.created_at,
          e.user_email ?? "",
          e.action,
          e.resource,
          String(e.status_code),
          e.ip_address,
          String(e.duration_ms ?? ""),
        ].join(","),
      );
    }
    const csv = csvRows.join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "audit-log.csv";
    a.click();
    URL.revokeObjectURL(url);
  }

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
      <DataTableToolbar
        table={table}
        searchPlaceholder="Search audit logs..."
        facetFilters={[
          { columnId: "action", title: "All actions", options: actionFacetOptions },
        ]}
      >
        <Button variant="outline" size="sm" onClick={exportCSV}>
          <Download className="mr-1.5 h-3.5 w-3.5" />
          Export CSV
        </Button>
      </DataTableToolbar>

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
                  No audit log entries found.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      <p className="text-xs text-muted-foreground">
        Showing {table.getFilteredRowModel().rows.length} of {data.length} entries
      </p>
    </div>
  );
}
