import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { apiClient } from "@/api/client";
import { Button } from "@/components/ui/button";
import { ResultSetTable } from "@/components/review/result-set-table";
import type { DocumentResponse, PaginatedResponse } from "@/types";

export const Route = createFileRoute("/review/result-set")({
  component: ResultSetPage,
});

function ResultSetPage() {
  const [offset, setOffset] = useState(0);
  const limit = 50;

  const { data, isLoading } = useQuery({
    queryKey: ["result-set", offset],
    queryFn: () =>
      apiClient<PaginatedResponse<DocumentResponse>>({
        url: "/api/v1/documents",
        method: "GET",
        params: { offset, limit },
      }),
  });

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold">Result Set</h1>
        <p className="text-sm text-muted-foreground">
          {data ? `${data.total} documents` : "Loading..."} &mdash; Select rows and export to CSV.
        </p>
      </div>

      <ResultSetTable data={data?.items ?? []} loading={isLoading} />

      {data && data.total > limit && (
        <div className="flex items-center justify-between">
          <span className="text-sm text-muted-foreground">
            Showing {offset + 1}&ndash;{Math.min(offset + limit, data.total)} of {data.total}
          </span>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - limit))}
            >
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={offset + limit >= data.total}
              onClick={() => setOffset(offset + limit)}
            >
              Next
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
