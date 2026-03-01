import { useMemo } from "react";
import { Link } from "@tanstack/react-router";
import {
  useReactTable,
  getCoreRowModel,
  flexRender,
  type ColumnDef,
} from "@tanstack/react-table";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { formatDate } from "@/lib/utils";
import type { EntityResponse } from "@/types";

const TYPE_COLORS: Record<string, string> = {
  PERSON: "bg-blue-500/15 text-blue-400 border-blue-500/30",
  ORG: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
  LOCATION: "bg-orange-500/15 text-orange-400 border-orange-500/30",
  DATE: "bg-violet-500/15 text-violet-400 border-violet-500/30",
  MONEY: "bg-pink-500/15 text-pink-400 border-pink-500/30",
};

function typeBadgeClass(type: string): string {
  return TYPE_COLORS[type] ?? "bg-slate-500/15 text-slate-400 border-slate-500/30";
}

interface EntityTableProps {
  data: EntityResponse[];
  loading?: boolean;
}

export function EntityTable({ data, loading }: EntityTableProps) {
  const columns = useMemo<ColumnDef<EntityResponse>[]>(
    () => [
      {
        accessorKey: "name",
        header: "Name",
        cell: ({ row }) => {
          const entity = row.original;
          const hasAliases = entity.aliases.length > 0;
          const nameLink = (
            <Link
              to="/entities/$id"
              params={{ id: entity.id }}
              className="font-medium text-primary hover:underline truncate block max-w-[280px]"
            >
              {entity.name}
            </Link>
          );

          if (!hasAliases) return nameLink;

          return (
            <Tooltip>
              <TooltipTrigger asChild>{nameLink}</TooltipTrigger>
              <TooltipContent side="right">
                <p className="text-xs font-medium mb-1">Aliases:</p>
                {entity.aliases.map((alias) => (
                  <p key={alias} className="text-xs">{alias}</p>
                ))}
              </TooltipContent>
            </Tooltip>
          );
        },
      },
      {
        accessorKey: "type",
        header: "Type",
        cell: ({ row }) => (
          <Badge variant="outline" className={`text-[10px] uppercase ${typeBadgeClass(row.original.type)}`}>
            {row.original.type}
          </Badge>
        ),
      },
      {
        accessorKey: "mention_count",
        header: "Mentions",
        cell: ({ row }) => (
          <span className="tabular-nums">{row.original.mention_count}</span>
        ),
      },
      {
        accessorKey: "first_seen",
        header: "First Seen",
        cell: ({ row }) =>
          row.original.first_seen ? (
            <span className="text-muted-foreground">
              {formatDate(row.original.first_seen)}
            </span>
          ) : (
            <span className="text-muted-foreground">--</span>
          ),
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
        {Array.from({ length: 10 }).map((_, i) => (
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
                    : flexRender(
                        header.column.columnDef.header,
                        header.getContext(),
                      )}
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
                    {flexRender(
                      cell.column.columnDef.cell,
                      cell.getContext(),
                    )}
                  </TableCell>
                ))}
              </TableRow>
            ))
          ) : (
            <TableRow>
              <TableCell
                colSpan={columns.length}
                className="h-24 text-center"
              >
                No entities found.
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </div>
  );
}
