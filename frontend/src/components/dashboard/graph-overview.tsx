import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { apiClient } from "@/api/client";
import { useAppStore } from "@/stores/app-store";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { MiniGraph } from "./mini-graph";
import type { GraphStats, EntityResponse, EntityConnection, PaginatedResponse } from "@/types";

export function GraphOverview() {
  const matterId = useAppStore((s) => s.matterId);

  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ["graph-stats", matterId],
    queryFn: () => apiClient<GraphStats>({ url: "/api/v1/graph/stats", method: "GET" }),
    enabled: !!matterId,
  });

  const { data: entitiesData, isLoading: entitiesLoading } = useQuery({
    queryKey: ["graph-overview-entities", matterId],
    queryFn: () =>
      apiClient<PaginatedResponse<EntityResponse>>({
        url: "/api/v1/entities",
        method: "GET",
        params: { limit: 20, offset: 0 },
      }),
    enabled: !!matterId,
  });

  const topEntityIds = useMemo(
    () =>
      (entitiesData?.items ?? [])
        .sort((a, b) => b.mention_count - a.mention_count)
        .slice(0, 10)
        .map((e) => e.id),
    [entitiesData],
  );

  const { data: connectionsData } = useQuery({
    queryKey: ["graph-overview-connections", topEntityIds],
    queryFn: async () => {
      const allConnections: EntityConnection[] = [];
      const seen = new Set<string>();

      const top = (entitiesData?.items ?? [])
        .sort((a, b) => b.mention_count - a.mention_count)
        .slice(0, 10);

      const results = await Promise.all(
        top.map((e) =>
          apiClient<{
            entity: EntityResponse;
            connections: EntityConnection[];
          }>({
            url: "/api/v1/entities/connections",
            method: "GET",
            params: { name: e.id, limit: 10 },
          }).catch(() => null),
        ),
      );

      for (const result of results) {
        if (!result) continue;
        for (const conn of result.connections) {
          const key = [conn.source, conn.target].sort().join("||");
          if (!seen.has(key)) {
            seen.add(key);
            allConnections.push(conn);
          }
        }
      }

      return allConnections;
    },
    enabled: !!entitiesData && entitiesData.items.length > 0,
  });

  const isLoading = statsLoading || entitiesLoading;
  const entities = entitiesData?.items ?? [];
  const connections = connectionsData ?? [];

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium">Knowledge Graph</CardTitle>
          <Link to="/entities" className="text-xs text-muted-foreground hover:text-foreground transition-colors">
            Explore
          </Link>
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-3">
            <Skeleton className="h-5 w-32" />
            <Skeleton className="h-5 w-24" />
            <Skeleton className="h-[180px] w-full" />
          </div>
        ) : stats && entities.length > 0 ? (
          <div className="space-y-3">
            <div className="flex gap-4">
              <div>
                <p className="text-2xl font-semibold tracking-tight tabular-nums">{(stats.total_nodes ?? 0).toLocaleString()}</p>
                <p className="text-xs text-muted-foreground">Entities</p>
              </div>
              <div>
                <p className="text-2xl font-semibold tracking-tight tabular-nums">{(stats.total_edges ?? 0).toLocaleString()}</p>
                <p className="text-xs text-muted-foreground">Relationships</p>
              </div>
            </div>
            <Link to="/entities" className="block rounded-md hover:bg-muted/50 transition-colors">
              <MiniGraph entities={entities} connections={connections} />
            </Link>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">No graph data available</p>
        )}
      </CardContent>
    </Card>
  );
}
