import { createLazyFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useState, useEffect } from "react";
import { useViewState } from "@/hooks/use-view-state";
import { ChevronDown, ChevronRight } from "lucide-react";
import { apiClient } from "@/api/client";
import { useAppStore } from "@/stores/app-store";
import { Pagination } from "@/components/ui/pagination";
import { ResultSetTable } from "@/components/review/result-set-table";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { DocumentResponse, PaginatedResponse } from "@/types";
import type { DuplicateCluster } from "@/api/generated/schemas";

export const Route = createLazyFileRoute("/review/result-set")({
  component: ResultSetPage,
});

function ResultSetPage() {
  const matterId = useAppStore((s) => s.matterId);
  const [vs, setVS] = useViewState("/review/result-set", {
    offset: 0,
    sorting: [],
    globalFilter: "",
  });
  const limit = 50;

  const { data, isLoading } = useQuery({
    queryKey: ["result-set", matterId, vs.offset],
    queryFn: () =>
      apiClient<PaginatedResponse<DocumentResponse>>({
        url: "/api/v1/documents",
        method: "GET",
        params: { offset: vs.offset, limit },
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
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Result Set</h1>
        <p className="text-sm text-muted-foreground">
          {data ? `${data.total} documents` : "Loading..."} &mdash; Select rows and export to CSV.
        </p>
      </div>

      <ResultSetTable
        data={data?.items ?? []}
        loading={isLoading}
        initialSorting={vs.sorting}
        onSortingChange={(s) => setVS({ sorting: s })}
        initialGlobalFilter={vs.globalFilter}
        onGlobalFilterChange={(f) => setVS({ globalFilter: f })}
      />

      {data && <Pagination total={data.total} offset={vs.offset} limit={limit} onOffsetChange={(o) => setVS({ offset: o })} />}

      <DuplicateClustersPanel />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Duplicate Clusters Panel
// ---------------------------------------------------------------------------

function DuplicateClustersPanel() {
  const [expandedCluster, setExpandedCluster] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["edrm-duplicates"],
    queryFn: () =>
      apiClient<PaginatedResponse<DuplicateCluster>>({
        url: "/api/v1/edrm/duplicates",
        method: "GET",
        params: { limit: 100 },
      }),
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Duplicate Clusters</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading && <p className="text-sm text-muted-foreground">Loading duplicates...</p>}
        {data && data.items.length === 0 && (
          <p className="text-sm text-muted-foreground">No duplicate clusters found.</p>
        )}
        {data && data.items.length > 0 && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-8" />
                <TableHead>Cluster ID</TableHead>
                <TableHead className="text-right">Documents</TableHead>
                <TableHead className="text-right">Avg Similarity</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.items.map((cluster) => {
                const isExpanded = expandedCluster === cluster.cluster_id;
                return (
                  <TableRow
                    key={cluster.cluster_id}
                    className="cursor-pointer"
                    onClick={() =>
                      setExpandedCluster(isExpanded ? null : cluster.cluster_id)
                    }
                  >
                    <TableCell className="w-8">
                      {isExpanded ? (
                        <ChevronDown className="h-4 w-4" />
                      ) : (
                        <ChevronRight className="h-4 w-4" />
                      )}
                    </TableCell>
                    <TableCell className="font-mono text-xs">{cluster.cluster_id}</TableCell>
                    <TableCell className="text-right">
                      <Badge variant="secondary">{cluster.document_count}</Badge>
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {cluster.avg_score != null ? cluster.avg_score.toFixed(3) : "--"}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
