import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
import { useAppStore } from "@/stores/app-store";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import type { GraphStats } from "@/types";

export function GraphOverview() {
  const matterId = useAppStore((s) => s.matterId);
  const { data, isLoading } = useQuery({
    queryKey: ["graph-stats", matterId],
    queryFn: () => apiClient<GraphStats>({ url: "/api/v1/graph/stats", method: "GET" }),
    enabled: !!matterId,
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-medium">Knowledge Graph</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-3">
            <Skeleton className="h-5 w-32" />
            <Skeleton className="h-5 w-24" />
            <Skeleton className="h-20 w-full" />
          </div>
        ) : data ? (
          <div className="space-y-3">
            <div className="flex gap-4">
              <div>
                <p className="text-2xl font-semibold tracking-tight tabular-nums">{(data.node_count ?? 0).toLocaleString()}</p>
                <p className="text-xs text-muted-foreground">Entities</p>
              </div>
              <div>
                <p className="text-2xl font-semibold tracking-tight tabular-nums">{(data.edge_count ?? 0).toLocaleString()}</p>
                <p className="text-xs text-muted-foreground">Relationships</p>
              </div>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {Object.entries(data.entity_types ?? {})
                .sort(([, a], [, b]) => b - a)
                .slice(0, 8)
                .map(([type, count]) => (
                  <Badge key={type} variant="secondary" className="text-[10px]">
                    {type}: {count}
                  </Badge>
                ))}
            </div>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">No graph data available</p>
        )}
      </CardContent>
    </Card>
  );
}
