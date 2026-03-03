import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Network } from "lucide-react";
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

export const Route = createFileRoute("/entities/")({
  component: EntitiesPage,
});

const ENTITY_TYPES = [
  { value: "all", label: "All Types" },
  { value: "person", label: "Person" },
  { value: "organization", label: "Organization" },
  { value: "location", label: "Location" },
  { value: "date", label: "Date" },
  { value: "monetary_amount", label: "Money" },
];

function EntitiesPage() {
  const matterId = useAppStore((s) => s.matterId);
  const [search, setSearch] = useState("");
  const debouncedSearch = useDebounce(search, 300);
  const [entityType, setEntityType] = useState("all");
  const [offset, setOffset] = useState(0);
  const limit = 50;

  const { data, isLoading } = useQuery({
    queryKey: ["entities", matterId, debouncedSearch, entityType, offset],
    queryFn: () =>
      apiClient<PaginatedResponse<EntityResponse>>({
        url: "/api/v1/entities",
        method: "GET",
        params: {
          q: debouncedSearch || undefined,
          entity_type: entityType !== "all" ? entityType : undefined,
          offset,
          limit,
        },
      }),
    enabled: !!matterId,
  });

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
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setOffset(0);
          }}
          className="max-w-sm"
        />
        <Select
          value={entityType}
          onValueChange={(v) => {
            setEntityType(v);
            setOffset(0);
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

      <EntityTable data={data?.items ?? []} loading={isLoading} />

      {data && <Pagination total={data.total} offset={offset} limit={limit} onOffsetChange={setOffset} />}
    </div>
  );
}
