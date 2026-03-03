import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { apiClient } from "@/api/client";
import { useAppStore } from "@/stores/app-store";
import { Pagination } from "@/components/ui/pagination";
import { ResultSetTable } from "@/components/review/result-set-table";
import type { DocumentResponse, PaginatedResponse } from "@/types";

export const Route = createFileRoute("/review/result-set")({
  component: ResultSetPage,
});

function ResultSetPage() {
  const matterId = useAppStore((s) => s.matterId);
  const [offset, setOffset] = useState(0);
  const limit = 50;

  const { data, isLoading } = useQuery({
    queryKey: ["result-set", matterId, offset],
    queryFn: () =>
      apiClient<PaginatedResponse<DocumentResponse>>({
        url: "/api/v1/documents",
        method: "GET",
        params: { offset, limit },
      }),
    enabled: !!matterId,
  });

  return (
    <div className="space-y-4 animate-page-in">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Result Set</h1>
        <p className="text-sm text-muted-foreground">
          {data ? `${data.total} documents` : "Loading..."} &mdash; Select rows and export to CSV.
        </p>
      </div>

      <ResultSetTable data={data?.items ?? []} loading={isLoading} />

      {data && <Pagination total={data.total} offset={offset} limit={limit} onOffsetChange={setOffset} />}
    </div>
  );
}
