import { useState } from "react";
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getFilteredRowModel,
  flexRender,
  createColumnHelper,
  type SortingState,
} from "@tanstack/react-table";
import type { User } from "@/types";
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
import { DataTableColumnHeader } from "@/components/ui/data-table-column-header";
import { DataTableToolbar } from "@/components/ui/data-table-toolbar";

const columnHelper = createColumnHelper<User>();

const columns = [
  columnHelper.accessor("email", {
    header: ({ column }) => <DataTableColumnHeader column={column} title="Email" />,
    cell: (info) => <span className="font-medium">{info.getValue()}</span>,
  }),
  columnHelper.accessor("full_name", {
    header: ({ column }) => <DataTableColumnHeader column={column} title="Full Name" />,
  }),
  columnHelper.accessor("role", {
    header: ({ column }) => <DataTableColumnHeader column={column} title="Role" />,
    cell: (info) => {
      const role = info.getValue();
      const variant =
        role === "admin"
          ? "default"
          : role === "attorney"
            ? "secondary"
            : "outline";
      return <Badge variant={variant}>{role}</Badge>;
    },
  }),
  columnHelper.accessor("is_active", {
    header: ({ column }) => <DataTableColumnHeader column={column} title="Status" />,
    cell: (info) => (
      <Badge variant={info.getValue() ? "default" : "destructive"}>
        {info.getValue() ? "Active" : "Inactive"}
      </Badge>
    ),
  }),
  columnHelper.accessor("created_at", {
    header: ({ column }) => <DataTableColumnHeader column={column} title="Created" />,
    cell: (info) => (
      <span className="text-muted-foreground">{formatDateTime(info.getValue())}</span>
    ),
  }),
];

interface UserTableProps {
  data: User[];
  isLoading: boolean;
  initialSorting?: SortingState;
  onSortingChange?: (sorting: SortingState) => void;
  initialGlobalFilter?: string;
  onGlobalFilterChange?: (filter: string) => void;
}

export function UserTable({ data, isLoading, initialSorting, onSortingChange, initialGlobalFilter, onGlobalFilterChange }: UserTableProps) {
  const [sorting, setSorting] = useState<SortingState>(initialSorting ?? []);
  const [globalFilter, setGlobalFilter] = useState(initialGlobalFilter ?? "");

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
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <DataTableToolbar table={table} searchPlaceholder="Search users..." />

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
                  No users found.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
