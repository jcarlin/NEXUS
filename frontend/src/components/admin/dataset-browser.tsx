import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getFilteredRowModel,
  flexRender,
  createColumnHelper,
  type SortingState,
} from "@tanstack/react-table";
import { apiClient } from "@/api/client";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
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
import type { DatasetItemResponse } from "@/api/generated/schemas";

const columnHelper = createColumnHelper<DatasetItemResponse>();

const columns = [
  columnHelper.accessor("question", {
    header: ({ column }) => <DataTableColumnHeader column={column} title="Question" />,
    cell: (info) => (
      <span className="text-sm">{info.getValue()}</span>
    ),
  }),
  columnHelper.accessor("expected_answer", {
    header: ({ column }) => <DataTableColumnHeader column={column} title="Expected Answer" />,
    cell: (info) => (
      <span className="max-w-[300px] truncate text-xs text-muted-foreground">
        {info.getValue()}
      </span>
    ),
  }),
  columnHelper.accessor("tags", {
    header: ({ column }) => <DataTableColumnHeader column={column} title="Tags" />,
    cell: (info) => (
      <div className="flex flex-wrap gap-1">
        {info.getValue().map((tag) => (
          <Badge key={tag} variant="outline" className="text-[10px]">
            {tag}
          </Badge>
        ))}
      </div>
    ),
    enableSorting: false,
  }),
];

function DatasetTab({ type }: { type: string }) {
  const [sorting, setSorting] = useState<SortingState>([]);
  const [globalFilter, setGlobalFilter] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["eval-dataset", type],
    queryFn: () =>
      apiClient<{ items: DatasetItemResponse[] }>({
        url: `/api/v1/evaluation/datasets/${type}`,
        method: "GET",
      }),
  });

  const table = useReactTable({
    data: data?.items ?? [],
    columns,
    state: { sorting, globalFilter },
    onSortingChange: setSorting,
    onGlobalFilterChange: setGlobalFilter,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
  });

  if (isLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-10 w-full" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <DataTableToolbar table={table} searchPlaceholder="Search dataset..." />

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
                  No items in this dataset.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}

export function DatasetBrowser() {
  return (
    <Tabs defaultValue="ground_truth">
      <TabsList>
        <TabsTrigger value="ground_truth">Ground Truth</TabsTrigger>
        <TabsTrigger value="adversarial">Adversarial</TabsTrigger>
        <TabsTrigger value="legalbench">LegalBench</TabsTrigger>
      </TabsList>
      <TabsContent value="ground_truth">
        <DatasetTab type="ground_truth" />
      </TabsContent>
      <TabsContent value="adversarial">
        <DatasetTab type="adversarial" />
      </TabsContent>
      <TabsContent value="legalbench">
        <DatasetTab type="legalbench" />
      </TabsContent>
    </Tabs>
  );
}
