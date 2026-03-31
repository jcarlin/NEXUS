import { useMemo, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getFilteredRowModel,
  flexRender,
  type ColumnDef,
  type SortingState,
} from "@tanstack/react-table";
import { apiClient } from "@/api/client";
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
import { formatNumber } from "@/lib/utils";
import { ProductionSetDetail } from "./production-set-detail";
import type { ProductionSet } from "@/routes/review/exports";

interface Props {
  data: ProductionSet[];
  loading: boolean;
  total: number;
  offset: number;
  limit: number;
  onOffsetChange: (offset: number) => void;
  onRefresh: () => void;
  initialSorting?: SortingState;
  onSortingChange?: (sorting: SortingState) => void;
  initialGlobalFilter?: string;
  onGlobalFilterChange?: (filter: string) => void;
}

const statusColors: Record<string, string> = {
  draft: "bg-yellow-500/15 text-yellow-700",
  finalized: "bg-blue-500/15 text-blue-700",
  exported: "bg-green-500/15 text-green-700",
};

export function ProductionSetList({
  data,
  loading,
  total,
  offset,
  limit,
  onOffsetChange,
  onRefresh,
  initialSorting,
  onSortingChange,
  initialGlobalFilter,
  onGlobalFilterChange,
}: Props) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [sorting, setSorting] = useState<SortingState>(initialSorting ?? []);
  const [globalFilter, setGlobalFilter] = useState(initialGlobalFilter ?? "");

  const batesMutation = useMutation({
    mutationFn: (psId: string) =>
      apiClient<ProductionSet>({
        url: `/api/v1/exports/production-sets/${psId}/assign-bates`,
        method: "POST",
      }),
    onSuccess: () => onRefresh(),
  });

  const columns = useMemo<ColumnDef<ProductionSet>[]>(
    () => [
      {
        accessorKey: "name",
        header: ({ column }) => <DataTableColumnHeader column={column} title="Name" />,
        cell: ({ row }) => <span className="font-medium">{row.original.name}</span>,
      },
      {
        accessorKey: "description",
        header: ({ column }) => <DataTableColumnHeader column={column} title="Description" />,
        cell: ({ row }) => (
          <span className="text-muted-foreground max-w-[200px] truncate block">
            {row.original.description || "\u2014"}
          </span>
        ),
      },
      {
        accessorKey: "document_count",
        header: ({ column }) => <DataTableColumnHeader column={column} title="Documents" />,
        cell: ({ row }) => <span className="tabular-nums">{formatNumber(row.original.document_count ?? 0)}</span>,
      },
      {
        accessorKey: "bates_prefix",
        header: ({ column }) => <DataTableColumnHeader column={column} title="Bates Prefix" />,
        cell: ({ row }) => (
          <span className="font-mono text-xs">{row.original.bates_prefix}</span>
        ),
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
        id: "actions",
        cell: ({ row }) =>
          row.original.status === "draft" ? (
            <Button
              variant="outline"
              size="sm"
              onClick={(e) => {
                e.stopPropagation();
                batesMutation.mutate(row.original.id);
              }}
              disabled={batesMutation.isPending}
            >
              Assign Bates
            </Button>
          ) : null,
        enableSorting: false,
        enableGlobalFilter: false,
      },
    ],
    [batesMutation],
  );

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

  if (selectedId) {
    return (
      <ProductionSetDetail
        productionSetId={selectedId}
        onBack={() => setSelectedId(null)}
        onRefresh={onRefresh}
      />
    );
  }

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
      <DataTableToolbar table={table} searchPlaceholder="Search production sets..." />

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
                <TableRow
                  key={row.id}
                  className="cursor-pointer hover:bg-muted/50"
                  onClick={() => setSelectedId(row.original.id)}
                >
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
                  No production sets yet. Create one to get started.
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
