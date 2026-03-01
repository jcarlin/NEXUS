import { useQuery } from "@tanstack/react-query";
import {
  useReactTable,
  getCoreRowModel,
  flexRender,
  createColumnHelper,
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

interface DatasetItem {
  question: string;
  expected_answer: string;
  tags: string[];
}

const columnHelper = createColumnHelper<DatasetItem>();

const columns = [
  columnHelper.accessor("question", {
    header: "Question",
    cell: (info) => (
      <span className="text-sm">{info.getValue()}</span>
    ),
  }),
  columnHelper.accessor("expected_answer", {
    header: "Expected Answer",
    cell: (info) => (
      <span className="max-w-[300px] truncate text-xs text-muted-foreground">
        {info.getValue()}
      </span>
    ),
  }),
  columnHelper.accessor("tags", {
    header: "Tags",
    cell: (info) => (
      <div className="flex flex-wrap gap-1">
        {info.getValue().map((tag) => (
          <Badge key={tag} variant="outline" className="text-[10px]">
            {tag}
          </Badge>
        ))}
      </div>
    ),
  }),
];

function DatasetTab({ type }: { type: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ["eval-dataset", type],
    queryFn: () =>
      apiClient<{ items: DatasetItem[] }>({
        url: `/api/v1/evaluation/datasets/${type}`,
        method: "GET",
      }),
  });

  const table = useReactTable({
    data: data?.items ?? [],
    columns,
    getCoreRowModel: getCoreRowModel(),
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
