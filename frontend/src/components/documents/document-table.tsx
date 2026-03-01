import { useMemo } from "react";
import { Link } from "@tanstack/react-router";
import {
  useReactTable,
  getCoreRowModel,
  flexRender,
  type ColumnDef,
} from "@tanstack/react-table";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDate } from "@/lib/utils";
import type { DocumentResponse } from "@/types";

function scoreColor(score: number | null | undefined): string {
  if (score == null) return "";
  if (score >= 0.8) return "text-red-400";
  if (score >= 0.5) return "text-yellow-400";
  return "text-muted-foreground";
}

function privilegeBadge(status: string | null | undefined) {
  if (!status) return null;
  const variant = status === "privileged" ? "destructive" : "secondary";
  return <Badge variant={variant} className="text-[10px]">{status}</Badge>;
}

interface DocumentTableProps {
  data: DocumentResponse[];
  loading?: boolean;
}

export function DocumentTable({ data, loading }: DocumentTableProps) {
  const columns = useMemo<ColumnDef<DocumentResponse>[]>(
    () => [
      {
        accessorKey: "filename",
        header: "Filename",
        cell: ({ row }) => (
          <Link
            to="/documents/$id"
            params={{ id: row.original.id }}
            className="font-medium text-primary hover:underline truncate block max-w-[300px]"
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
            {row.original.type ?? "—"}
          </Badge>
        ),
      },
      { accessorKey: "page_count", header: "Pages" },
      {
        id: "hot_doc_score",
        header: "Hot Score",
        cell: ({ row }) => {
          const doc = row.original as DocumentResponse & { hot_doc_score?: number | null };
          const score = doc.hot_doc_score;
          return score != null ? (
            <span className={scoreColor(score)}>{score.toFixed(2)}</span>
          ) : (
            <span className="text-muted-foreground">—</span>
          );
        },
      },
      {
        accessorKey: "privilege_status",
        header: "Privilege",
        cell: ({ row }) => privilegeBadge(row.original.privilege_status) ?? <span className="text-muted-foreground">—</span>,
      },
      {
        accessorKey: "created_at",
        header: "Date",
        cell: ({ row }) => <span className="text-muted-foreground">{formatDate(row.original.created_at)}</span>,
      },
    ],
    [],
  );

  const table = useReactTable({
    data,
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

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
    <div className="rounded-md border">
      <Table>
        <TableHeader>
          {table.getHeaderGroups().map((headerGroup) => (
            <TableRow key={headerGroup.id}>
              {headerGroup.headers.map((header) => (
                <TableHead key={header.id}>
                  {header.isPlaceholder ? null : flexRender(header.column.columnDef.header, header.getContext())}
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
                No documents found.
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </div>
  );
}
