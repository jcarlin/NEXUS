import { useState } from "react";
import {
  useReactTable,
  getCoreRowModel,
  flexRender,
  createColumnHelper,
} from "@tanstack/react-table";
import { Download, Search } from "lucide-react";
import type { AuditLogEntry } from "@/types";
import { formatDateTime, cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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
import { Skeleton } from "@/components/ui/skeleton";

const columnHelper = createColumnHelper<AuditLogEntry>();

function statusColor(code: number): string {
  if (code >= 200 && code < 300) return "text-green-500";
  if (code >= 400 && code < 500) return "text-yellow-500";
  return "text-red-500";
}

const columns = [
  columnHelper.accessor("created_at", {
    header: "Timestamp",
    cell: (info) => (
      <span className="whitespace-nowrap text-xs">{formatDateTime(info.getValue())}</span>
    ),
  }),
  columnHelper.accessor("user_email", {
    header: "User",
    cell: (info) => (
      <span className="text-sm">{info.getValue() ?? "anonymous"}</span>
    ),
  }),
  columnHelper.accessor("action", {
    header: "Action",
    cell: (info) => (
      <Badge variant="outline" className="font-mono text-[10px]">
        {info.getValue()}
      </Badge>
    ),
  }),
  columnHelper.accessor("resource", {
    header: "Resource",
    cell: (info) => (
      <span className="max-w-[200px] truncate text-xs text-muted-foreground">
        {info.getValue()}
      </span>
    ),
  }),
  columnHelper.accessor("status_code", {
    header: "Status",
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
    header: "IP",
    cell: (info) => (
      <span className="font-mono text-xs text-muted-foreground">{info.getValue()}</span>
    ),
  }),
  columnHelper.accessor("duration_ms", {
    header: "Duration",
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
  const [emailFilter, setEmailFilter] = useState("");
  const [actionFilter, setActionFilter] = useState<string>("all");

  const filtered = data.filter((entry) => {
    if (emailFilter && !entry.user_email?.toLowerCase().includes(emailFilter.toLowerCase())) {
      return false;
    }
    if (actionFilter !== "all" && entry.action !== actionFilter) {
      return false;
    }
    return true;
  });

  const actions = [...new Set(data.map((e) => e.action))].sort();

  const table = useReactTable({
    data: filtered,
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  function exportCSV() {
    const headers = ["timestamp", "user_email", "action", "resource", "status_code", "ip_address", "duration_ms"];
    const rows = filtered.map((e) => [
      e.created_at,
      e.user_email ?? "",
      e.action,
      e.resource,
      String(e.status_code),
      e.ip_address,
      String(e.duration_ms ?? ""),
    ]);
    const csv = [headers.join(","), ...rows.map((r) => r.join(","))].join("\n");
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
      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[200px] max-w-xs">
          <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Filter by email..."
            value={emailFilter}
            onChange={(e) => setEmailFilter(e.target.value)}
            className="pl-8"
          />
        </div>
        <Select value={actionFilter} onValueChange={setActionFilter}>
          <SelectTrigger className="w-[180px]">
            <SelectValue placeholder="All actions" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All actions</SelectItem>
            {actions.map((action) => (
              <SelectItem key={action} value={action}>
                {action}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button variant="outline" size="sm" onClick={exportCSV}>
          <Download className="mr-1.5 h-3.5 w-3.5" />
          Export CSV
        </Button>
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
                  No audit log entries found.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      <p className="text-xs text-muted-foreground">
        Showing {filtered.length} of {data.length} entries
      </p>
    </div>
  );
}
