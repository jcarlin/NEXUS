import { Fragment, useMemo, useState } from "react";
import { Link } from "@tanstack/react-router";
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getFilteredRowModel,
  getExpandedRowModel,
  flexRender,
  type ColumnDef,
  type SortingState,
} from "@tanstack/react-table";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { DataTableColumnHeader } from "@/components/ui/data-table-column-header";
import { DataTableToolbar } from "@/components/ui/data-table-toolbar";
import { SentimentSparklines } from "@/components/review/sentiment-sparklines";
import { formatDate } from "@/lib/utils";
import type { DocumentDetail } from "@/types";

export function hotDocScoreColor(score: number | null | undefined): string {
  if (score == null) return "text-muted-foreground";
  if (score >= 0.8) return "text-red-400";
  if (score >= 0.5) return "text-yellow-400";
  return "text-muted-foreground";
}

interface HotDocTableProps {
  data: DocumentDetail[];
  loading?: boolean;
}

export function HotDocTable({ data, loading }: HotDocTableProps) {
  const [sorting, setSorting] = useState<SortingState>([
    { id: "hot_doc_score", desc: true },
  ]);
  const [globalFilter, setGlobalFilter] = useState("");

  const columns = useMemo<ColumnDef<DocumentDetail>[]>(
    () => [
      {
        accessorKey: "filename",
        header: ({ column }) => <DataTableColumnHeader column={column} title="Filename" />,
        cell: ({ row }) => (
          <Link
            to="/documents/$id"
            params={{ id: row.original.id }}
            className="font-medium text-primary hover:underline truncate block max-w-[260px]"
          >
            {row.original.filename}
          </Link>
        ),
        enableSorting: false,
      },
      {
        accessorKey: "type",
        header: ({ column }) => <DataTableColumnHeader column={column} title="Type" />,
        cell: ({ row }) => (
          <Badge variant="outline" className="text-[10px] uppercase">
            {row.original.type ?? "--"}
          </Badge>
        ),
        enableSorting: false,
      },
      {
        accessorKey: "hot_doc_score",
        header: ({ column }) => <DataTableColumnHeader column={column} title="Hot Score" />,
        cell: ({ row }) => {
          const score = row.original.hot_doc_score;
          return score != null ? (
            <span className={`font-mono font-medium ${hotDocScoreColor(score)}`}>
              {score.toFixed(2)}
            </span>
          ) : (
            <span className="text-muted-foreground">--</span>
          );
        },
        sortingFn: "basic",
      },
      {
        accessorKey: "anomaly_score",
        header: ({ column }) => <DataTableColumnHeader column={column} title="Anomaly" />,
        cell: ({ row }) => {
          const score = row.original.anomaly_score;
          return score != null ? (
            <span className="font-mono text-sm">{score.toFixed(2)}</span>
          ) : (
            <span className="text-muted-foreground">--</span>
          );
        },
        sortingFn: "basic",
      },
      {
        accessorKey: "privilege_status",
        header: ({ column }) => <DataTableColumnHeader column={column} title="Privilege" />,
        cell: ({ row }) => {
          const status = row.original.privilege_status;
          if (!status) return <span className="text-muted-foreground">--</span>;
          return (
            <Badge variant={status === "privileged" ? "destructive" : "secondary"} className="text-[10px]">
              {status}
            </Badge>
          );
        },
        enableSorting: false,
      },
      {
        accessorKey: "created_at",
        header: ({ column }) => <DataTableColumnHeader column={column} title="Date" />,
        cell: ({ row }) => (
          <span className="text-muted-foreground text-sm">
            {formatDate(row.original.created_at)}
          </span>
        ),
        sortingFn: "datetime",
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
    getExpandedRowModel: getExpandedRowModel(),
    getRowCanExpand: () => true,
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
    <div className="space-y-4">
      <DataTableToolbar table={table} searchPlaceholder="Search hot documents..." />

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
                  <TableRow
                    className="cursor-pointer"
                    onClick={() => row.toggleExpanded()}
                  >
                    {row.getVisibleCells().map((cell) => (
                      <TableCell key={cell.id}>
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </TableCell>
                    ))}
                  </TableRow>
                  {row.getIsExpanded() && (
                    <TableRow key={`${row.id}-expanded`}>
                      <TableCell colSpan={columns.length} className="bg-muted/30 p-4">
                        <div className="flex items-start gap-6">
                          <div>
                            <p className="text-xs font-medium text-muted-foreground mb-1">Sentiment</p>
                            <SentimentSparklines
                              positive={row.original.sentiment_positive}
                              negative={row.original.sentiment_negative}
                              pressure={row.original.sentiment_pressure}
                              opportunity={row.original.sentiment_opportunity}
                              rationalization={row.original.sentiment_rationalization}
                              intent={row.original.sentiment_intent}
                              concealment={row.original.sentiment_concealment}
                            />
                          </div>
                          {row.original.context_gaps && row.original.context_gaps.length > 0 && (
                            <div>
                              <p className="text-xs font-medium text-muted-foreground mb-1">Context Gaps</p>
                              <ul className="text-xs space-y-0.5">
                                {row.original.context_gaps.map((gap, i) => (
                                  <li key={i} className="text-muted-foreground">{gap}</li>
                                ))}
                              </ul>
                            </div>
                          )}
                        </div>
                      </TableCell>
                    </TableRow>
                  )}
                </Fragment>
              ))
            ) : (
              <TableRow>
                <TableCell colSpan={columns.length} className="h-24 text-center">
                  No hot documents found.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
