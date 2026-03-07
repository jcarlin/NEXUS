import {
  useReactTable,
  getCoreRowModel,
  flexRender,
  createColumnHelper,
} from "@tanstack/react-table";
import { formatDateTime } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import type { EvalRunResponse } from "@/api/generated/schemas";

const columnHelper = createColumnHelper<EvalRunResponse>();

const columns = [
  columnHelper.accessor("id", {
    header: "Run ID",
    cell: (info) => (
      <span className="font-mono text-xs">{info.getValue().slice(0, 8)}</span>
    ),
  }),
  columnHelper.accessor("mode", {
    header: "Mode",
    cell: (info) => (
      <Badge variant="outline">{info.getValue()}</Badge>
    ),
  }),
  columnHelper.accessor("created_at", {
    header: "Created",
    cell: (info) => (
      <span className="text-xs text-muted-foreground">{formatDateTime(info.getValue())}</span>
    ),
  }),
  columnHelper.accessor("status", {
    header: "Status",
    cell: (info) => {
      const status = info.getValue();
      const variant =
        status === "completed"
          ? "default"
          : status === "running"
            ? "secondary"
            : "destructive";
      return <Badge variant={variant}>{status}</Badge>;
    },
  }),
  columnHelper.accessor("metrics", {
    header: "Metrics Summary",
    cell: (info) => {
      const raw = info.getValue();
      const metrics = (raw ?? {}) as Record<string, number>;
      const keys = Object.keys(metrics).slice(0, 3);
      return (
        <div className="flex gap-2">
          {keys.map((k) => (
            <span key={k} className="text-xs text-muted-foreground">
              {k}: {((metrics[k] ?? 0) * 100).toFixed(0)}%
            </span>
          ))}
        </div>
      );
    },
  }),
];

interface RunHistoryProps {
  data: EvalRunResponse[];
  isLoading: boolean;
}

export function RunHistory({ data, isLoading }: RunHistoryProps) {
  const table = useReactTable({
    data,
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  if (isLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-10 w-full" />
        ))}
      </div>
    );
  }

  return (
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
                No evaluation runs found.
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </div>
  );
}
