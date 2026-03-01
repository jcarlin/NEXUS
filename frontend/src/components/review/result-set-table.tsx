import { useMemo, useState, useCallback } from "react";
import { Link } from "@tanstack/react-router";
import {
  useReactTable,
  getCoreRowModel,
  flexRender,
  type ColumnDef,
  type RowSelectionState,
} from "@tanstack/react-table";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Skeleton } from "@/components/ui/skeleton";
import { Download } from "lucide-react";
import { formatDate } from "@/lib/utils";
import type { DocumentResponse } from "@/types";

interface ResultSetTableProps {
  data: DocumentResponse[];
  loading?: boolean;
}

export function ResultSetTable({ data, loading }: ResultSetTableProps) {
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});

  const columns = useMemo<ColumnDef<DocumentResponse>[]>(
    () => [
      {
        id: "select",
        header: ({ table }) => (
          <Checkbox
            checked={table.getIsAllRowsSelected()}
            onCheckedChange={(value) => table.toggleAllRowsSelected(!!value)}
            aria-label="Select all"
          />
        ),
        cell: ({ row }) => (
          <Checkbox
            checked={row.getIsSelected()}
            onCheckedChange={(value) => row.toggleSelected(!!value)}
            aria-label="Select row"
          />
        ),
        enableSorting: false,
      },
      {
        accessorKey: "filename",
        header: "Filename",
        cell: ({ row }) => (
          <Link
            to="/documents/$id"
            params={{ id: row.original.id }}
            className="font-medium text-primary hover:underline truncate block max-w-[260px]"
          >
            {row.original.filename}
          </Link>
        ),
      },
      {
        accessorKey: "type",
        header: "Type",
        cell: ({ row }) => (
          <Badge variant="outline" className="text-[10px] uppercase">
            {row.original.type ?? "--"}
          </Badge>
        ),
      },
      {
        accessorKey: "created_at",
        header: "Date",
        cell: ({ row }) => (
          <span className="text-muted-foreground text-sm">
            {formatDate(row.original.created_at)}
          </span>
        ),
      },
      {
        id: "hot_doc_score",
        header: "Hot Score",
        cell: ({ row }) => {
          const doc = row.original as DocumentResponse & { hot_doc_score?: number | null };
          const score = doc.hot_doc_score;
          if (score == null) return <span className="text-muted-foreground">--</span>;
          const color =
            score >= 0.8 ? "text-red-400" : score >= 0.5 ? "text-yellow-400" : "text-muted-foreground";
          return <span className={`font-mono ${color}`}>{score.toFixed(2)}</span>;
        },
      },
      {
        id: "anomaly_score",
        header: "Anomaly",
        cell: ({ row }) => {
          const doc = row.original as DocumentResponse & { anomaly_score?: number | null };
          const score = doc.anomaly_score;
          return score != null ? (
            <span className="font-mono text-sm">{score.toFixed(2)}</span>
          ) : (
            <span className="text-muted-foreground">--</span>
          );
        },
      },
      {
        id: "dedup",
        header: "Dedup",
        cell: ({ row }) =>
          row.original.duplicate_cluster_id ? (
            <Badge variant="secondary" className="text-[10px]">Dup</Badge>
          ) : null,
      },
    ],
    [],
  );

  const table = useReactTable({
    data,
    columns,
    state: { rowSelection },
    onRowSelectionChange: setRowSelection,
    getCoreRowModel: getCoreRowModel(),
    enableRowSelection: true,
    getRowId: (row) => row.id,
  });

  const selectedRows = table.getSelectedRowModel().rows;

  const handleExport = useCallback(() => {
    if (selectedRows.length === 0) return;

    const headers = ["id", "filename", "type", "created_at", "page_count", "chunk_count", "privilege_status", "duplicate_cluster_id"];
    const csvRows = [headers.join(",")];

    for (const row of selectedRows) {
      const doc = row.original;
      csvRows.push(
        [
          doc.id,
          `"${doc.filename.replace(/"/g, '""')}"`,
          doc.type ?? "",
          doc.created_at,
          doc.page_count,
          doc.chunk_count,
          doc.privilege_status ?? "",
          doc.duplicate_cluster_id ?? "",
        ].join(","),
      );
    }

    const blob = new Blob([csvRows.join("\n")], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "result-set-export.csv";
    a.click();
    URL.revokeObjectURL(url);
  }, [selectedRows]);

  if (loading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 8 }).map((_, i) => (
          <Skeleton key={i} className="h-10 w-full" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {selectedRows.length > 0 && (
        <div className="flex items-center gap-3">
          <span className="text-sm text-muted-foreground">
            {selectedRows.length} selected
          </span>
          <Button size="sm" variant="outline" onClick={handleExport}>
            <Download className="mr-2 h-3 w-3" />
            Export CSV
          </Button>
        </div>
      )}

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
                <TableRow key={row.id} data-state={row.getIsSelected() && "selected"}>
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
                  No documents found.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
