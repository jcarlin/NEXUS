import { useMemo, useState } from "react";
import { Link } from "@tanstack/react-router";
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  flexRender,
  type ColumnDef,
  type SortingState,
} from "@tanstack/react-table";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { LoadingState } from "@/components/ui/loading-state";
import { DataTableColumnHeader } from "@/components/ui/data-table-column-header";
import { formatDate, formatFileSize, formatNumber } from "@/lib/utils";
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
  initialSorting?: SortingState;
  onSortingChange?: (sorting: SortingState) => void;
}

export function DocumentTable({ data, loading, initialSorting, onSortingChange }: DocumentTableProps) {
  const [sorting, setSorting] = useState<SortingState>(initialSorting ?? []);

  const columns = useMemo<ColumnDef<DocumentResponse>[]>(
    () => [
      {
        accessorKey: "filename",
        header: ({ column }) => <DataTableColumnHeader column={column} title="Filename" />,
        cell: ({ row }) => (
          <div className="max-w-[300px]">
            <Link
              to="/documents/$id"
              params={{ id: row.original.id }}
              className="font-medium text-primary hover:underline truncate block"
            >
              {row.original.filename}
            </Link>
            {row.original.summary && (
              <p className="text-xs text-muted-foreground truncate mt-0.5">{row.original.summary}</p>
            )}
          </div>
        ),
      },
      {
        id: "extension",
        header: ({ column }) => <DataTableColumnHeader column={column} title="Type" />,
        accessorFn: (row) => row.filename?.split(".").pop()?.toUpperCase() ?? "",
        cell: ({ row }) => {
          const ext = row.original.filename?.split(".").pop()?.toUpperCase();
          return (
            <Badge variant="outline" className="text-[10px] uppercase">
              {ext ?? "\u2014"}
            </Badge>
          );
        },
      },
      {
        accessorKey: "page_count",
        header: ({ column }) => <DataTableColumnHeader column={column} title="Pages" />,
        cell: ({ row }) => {
          const count = row.original.page_count;
          return count != null ? <span className="tabular-nums">{formatNumber(count)}</span> : <span className="text-muted-foreground">{"\u2014"}</span>;
        },
      },
      {
        accessorKey: "file_size_bytes",
        header: ({ column }) => <DataTableColumnHeader column={column} title="Size" />,
        cell: ({ row }) => {
          const bytes = (row.original as DocumentResponse & { file_size_bytes?: number | null }).file_size_bytes;
          if (bytes == null) return <span className="text-muted-foreground">{"\u2014"}</span>;
          return <span className="text-muted-foreground">{formatFileSize(bytes)}</span>;
        },
      },
      {
        id: "hot_doc_score",
        header: ({ column }) => <DataTableColumnHeader column={column} title="Hot Score" />,
        accessorFn: (row) => (row as DocumentResponse & { hot_doc_score?: number | null }).hot_doc_score,
        cell: ({ row }) => {
          const doc = row.original as DocumentResponse & { hot_doc_score?: number | null };
          const score = doc.hot_doc_score;
          return score != null ? (
            <span className={scoreColor(score)}>{score.toFixed(2)}</span>
          ) : (
            <span className="text-muted-foreground">{"\u2014"}</span>
          );
        },
      },
      {
        accessorKey: "privilege_status",
        header: ({ column }) => <DataTableColumnHeader column={column} title="Privilege" className="hidden md:table-cell" />,
        cell: ({ row }) => <div className="hidden md:table-cell">{privilegeBadge(row.original.privilege_status) ?? <span className="text-muted-foreground">{"\u2014"}</span>}</div>,
      },
      {
        accessorKey: "created_at",
        header: ({ column }) => <DataTableColumnHeader column={column} title="Date" className="hidden md:table-cell" />,
        cell: ({ row }) => <div className="hidden md:table-cell"><span className="text-muted-foreground">{formatDate(row.original.created_at)}</span></div>,
      },
    ],
    [],
  );

  const table = useReactTable({
    data,
    columns,
    state: { sorting },
    onSortingChange: (updater) => {
      const next = typeof updater === "function" ? updater(sorting) : updater;
      setSorting(next);
      onSortingChange?.(next);
    },
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  if (loading) {
    return (
      <div className="space-y-4">
        <LoadingState
          messages={[
            "Querying document index...",
            "Fetching metadata and classifications...",
            "Loading privilege status...",
            "Building document table...",
          ]}
          className="py-12"
        />
        <div className="space-y-2 opacity-30">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-10 w-full" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="overflow-x-auto rounded-md border">
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
    </div>
  );
}
