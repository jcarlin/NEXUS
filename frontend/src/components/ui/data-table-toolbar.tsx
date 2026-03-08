import { type Table } from "@tanstack/react-table";
import { Search, X } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

interface FacetFilter {
  columnId: string;
  title: string;
  options: { label: string; value: string }[];
}

interface DataTableToolbarProps<TData> {
  table: Table<TData>;
  searchPlaceholder?: string;
  facetFilters?: FacetFilter[];
  children?: React.ReactNode;
}

export function DataTableToolbar<TData>({
  table,
  searchPlaceholder = "Search...",
  facetFilters,
  children,
}: DataTableToolbarProps<TData>) {
  const globalFilter = (table.getState().globalFilter as string) ?? "";
  const isFiltered = globalFilter.length > 0 || facetFilters?.some(
    (f) => table.getColumn(f.columnId)?.getFilterValue() != null,
  );

  return (
    <div className="flex flex-wrap items-center gap-3">
      <div className="relative flex-1 min-w-[200px] max-w-xs">
        <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
        <Input
          placeholder={searchPlaceholder}
          value={globalFilter}
          onChange={(e) => table.setGlobalFilter(e.target.value)}
          className="pl-8"
        />
      </div>

      {facetFilters?.map((facet) => {
        const column = table.getColumn(facet.columnId);
        if (!column) return null;
        const value = (column.getFilterValue() as string) ?? "all";
        return (
          <Select
            key={facet.columnId}
            value={value}
            onValueChange={(v) => column.setFilterValue(v === "all" ? undefined : v)}
          >
            <SelectTrigger className="w-[160px]">
              <SelectValue placeholder={facet.title} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{facet.title}</SelectItem>
              {facet.options.map((opt) => (
                <SelectItem key={opt.value} value={opt.value}>
                  {opt.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        );
      })}

      {isFiltered && (
        <Button
          variant="ghost"
          size="sm"
          onClick={() => {
            table.setGlobalFilter("");
            facetFilters?.forEach((f) => table.getColumn(f.columnId)?.setFilterValue(undefined));
          }}
        >
          Clear
          <X className="ml-1.5 h-3.5 w-3.5" />
        </Button>
      )}

      {children}
    </div>
  );
}
