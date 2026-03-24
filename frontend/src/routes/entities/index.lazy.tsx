import { createLazyFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useState, useEffect } from "react";
import { Network } from "lucide-react";
import { useViewState } from "@/hooks/use-view-state";
import { apiClient } from "@/api/client";
import { useAppStore } from "@/stores/app-store";
import { useDebounce } from "@/hooks/use-debounce";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Pagination } from "@/components/ui/pagination";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { EntityTable } from "@/components/entities/entity-table";
import type { EntityResponse, PaginatedResponse } from "@/types";

export const Route = createLazyFileRoute("/entities/")({
  component: EntitiesPage,
});

const ENTITY_TYPES = [
  { value: "all", label: "All Types" },
  { value: "person", label: "Person" },
  { value: "organization", label: "Organization" },
  { value: "location", label: "Location" },
  { value: "date", label: "Date" },
  { value: "monetary_amount", label: "Money" },
  { value: "email_address", label: "Email" },
  { value: "phone_number", label: "Phone" },
  { value: "address", label: "Address" },
];

function EntitiesPage() {
  const matterId = useAppStore((s) => s.matterId);
  const [vs, setVS] = useViewState("/entities", {
    search: "",
    entityType: "all",
    offset: 0,
    sorting: [],
  });
  const [searchInput, setSearchInput] = useState(vs.search);
  const debouncedSearch = useDebounce(searchInput, 300);
  const limit = 50;

  // Sync debounced search back to persisted view state
  useEffect(() => {
    setVS({ search: debouncedSearch });
  }, [debouncedSearch, setVS]);

  const { data, isLoading } = useQuery({
    queryKey: ["entities", matterId, debouncedSearch, vs.entityType, vs.offset],
    queryFn: () =>
      apiClient<PaginatedResponse<EntityResponse>>({
        url: "/api/v1/entities",
        method: "GET",
        params: {
          q: debouncedSearch || undefined,
          entity_type: vs.entityType !== "all" ? vs.entityType : undefined,
          offset: vs.offset,
          limit,
        },
      }),
    enabled: !!matterId,
  });

  // Safety guard: reset offset if it points beyond available data
  useEffect(() => {
    if (data && data.items.length === 0 && data.total > 0 && vs.offset > 0) {
      setVS({ offset: 0 });
    }
  }, [data, vs.offset, setVS]);

  return (
    <div className="space-y-4 animate-page-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Entities</h1>
          <p className="text-sm text-muted-foreground">
            {data ? `${data.total} entities` : "Loading..."}
          </p>
        </div>
        <Button variant="outline" asChild>
          <Link to="/entities/network">
            <Network className="mr-2 h-4 w-4" />
            Network Graph
          </Link>
        </Button>
      </div>

      <div className="flex items-center gap-3">
        <Input
          placeholder="Search entities..."
          value={searchInput}
          onChange={(e) => {
            setSearchInput(e.target.value);
            setVS({ offset: 0 });
          }}
          className="max-w-sm"
        />
        <Select
          value={vs.entityType}
          onValueChange={(v) => {
            setVS({ entityType: v, offset: 0 });
          }}
        >
          <SelectTrigger className="w-[180px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {ENTITY_TYPES.map((t) => (
              <SelectItem key={t.value} value={t.value}>
                {t.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <EntityTable
        data={data?.items ?? []}
        loading={isLoading}
        initialSorting={vs.sorting}
        onSortingChange={(s) => setVS({ sorting: s })}
      />

      {data && <Pagination total={data.total} offset={vs.offset} limit={limit} onOffsetChange={(o) => setVS({ offset: o })} />}
    </div>
  );
}
