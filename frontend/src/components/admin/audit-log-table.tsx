import { useMemo, useState, useCallback } from "react";
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
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { apiFetchRaw } from "@/api/client";

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
        <span className="text-xs text-muted-foreground">{ms.toLocaleString()}ms</span>
      ) : (
        <span className="text-xs text-muted-foreground">-</span>
      );
    },
  }),
];

interface AuditLogTableProps {
  data: AuditLogEntry[];
  isLoading: boolean;
  initialSorting?: SortingState;
  onSortingChange?: (sorting: SortingState) => void;
  initialGlobalFilter?: string;
  onGlobalFilterChange?: (filter: string) => void;
}

export function AuditLogTable({ data, isLoading, initialSorting, onSortingChange, initialGlobalFilter, onGlobalFilterChange }: AuditLogTableProps) {
  const [sorting, setSorting] = useState<SortingState>(initialSorting ?? []);
  const [globalFilter, setGlobalFilter] = useState(initialGlobalFilter ?? "");
  const [exportDialogOpen, setExportDialogOpen] = useState(false);

  const actionFacetOptions = useMemo(() => {
    const actions = [...new Set(data.map((e) => e.action))].sort();
    return actions.map((a) => ({ label: a, value: a }));
  }, [data]);

  const table = useReactTable({
    data,
    columns,
    state: { sorting, globalFilter },
    onSortingChange: (updater) => {
      const next = typeof updater === "function" ? updater(sorting) : updater;
      setSorting(next);
      onSortingChange?.(next);
    },
    onGlobalFilterChange: (updater) => {
      const next = typeof updater === "function" ? updater(globalFilter) : updater;
      setGlobalFilter(next);
      onGlobalFilterChange?.(next);
    },
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
  });

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
        <Button
          variant="outline"
          size="sm"
          onClick={() => setExportDialogOpen(true)}
          data-testid="server-export-button"
        >
          <Download className="mr-1.5 h-3.5 w-3.5" />
          Export
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

      <AuditExportDialog
        open={exportDialogOpen}
        onOpenChange={setExportDialogOpen}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Server-side audit export dialog
// ---------------------------------------------------------------------------

interface AuditExportDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function AuditExportDialog({ open, onOpenChange }: AuditExportDialogProps) {
  const [format, setFormat] = useState<"csv" | "json">("csv");
  const [table, setTable] = useState("audit_log");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [isExporting, setIsExporting] = useState(false);

  const handleExport = useCallback(async () => {
    setIsExporting(true);
    try {
      const params = new URLSearchParams();
      params.set("format", format);
      params.set("table", table);
      if (startDate) params.set("date_from", new Date(startDate).toISOString());
      if (endDate) params.set("date_to", new Date(endDate).toISOString());

      const res = await apiFetchRaw(
        `/api/v1/admin/audit/export?${params.toString()}`,
      );
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${table}_export.${format}`;
      a.click();
      URL.revokeObjectURL(url);
      onOpenChange(false);
    } finally {
      setIsExporting(false);
    }
  }, [format, table, startDate, endDate, onOpenChange]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="audit-export-dialog" className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Export Audit Logs</DialogTitle>
          <DialogDescription>
            Download audit log data from the server with optional date range filtering.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* Table selector */}
          <div className="space-y-2">
            <Label htmlFor="export-table">Log Table</Label>
            <Select value={table} onValueChange={setTable}>
              <SelectTrigger id="export-table" data-testid="export-table-select">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="audit_log">API Audit Log</SelectItem>
                <SelectItem value="ai_audit_log">AI Audit Log</SelectItem>
                <SelectItem value="agent_audit_log">Agent Audit Log</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* Format selector */}
          <div className="space-y-2">
            <Label htmlFor="export-format">Format</Label>
            <Select value={format} onValueChange={(v) => setFormat(v as "csv" | "json")}>
              <SelectTrigger id="export-format" data-testid="export-format-select">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="csv">CSV</SelectItem>
                <SelectItem value="json">JSON</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* Date range */}
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="export-start-date">Start Date</Label>
              <input
                id="export-start-date"
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                data-testid="export-start-date"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="export-end-date">End Date</Label>
              <input
                id="export-end-date"
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                data-testid="export-end-date"
              />
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
          >
            Cancel
          </Button>
          <Button
            onClick={handleExport}
            disabled={isExporting}
            data-testid="export-submit"
          >
            <Download className="mr-1.5 h-3.5 w-3.5" />
            {isExporting ? "Exporting..." : "Export"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
