import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useState, useCallback, useRef } from "react";
import { ArrowLeft } from "lucide-react";
import { apiClient } from "@/api/client";
import { useAppStore } from "@/stores/app-store";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  NetworkGraph,
  type NetworkGraphHandle,
} from "@/components/entities/network-graph";
import { GraphControls } from "@/components/entities/graph-controls";
import type {
  EntityResponse,
  EntityConnection,
  PaginatedResponse,
} from "@/types";

export const Route = createFileRoute("/entities/network")({
  component: NetworkGraphPage,
});

const DEFAULT_TYPES = new Set(["PERSON", "ORG", "LOCATION", "DATE", "MONEY"]);

function NetworkGraphPage() {
  const matterId = useAppStore((s) => s.matterId);
  const [activeTypes, setActiveTypes] = useState<Set<string>>(
    () => new Set(DEFAULT_TYPES),
  );
  const graphRef = useRef<NetworkGraphHandle>(null);

  const { data: entitiesData, isLoading: entitiesLoading } = useQuery({
    queryKey: ["entities-network", matterId],
    queryFn: () =>
      apiClient<PaginatedResponse<EntityResponse>>({
        url: "/api/v1/entities",
        method: "GET",
        params: { limit: 200, offset: 0 },
      }),
    enabled: !!matterId,
  });

  // Fetch connections for top entities by mention count
  const entityIds = entitiesData?.items.map((e) => e.id) ?? [];
  const { data: connectionsData, isLoading: connectionsLoading } = useQuery({
    queryKey: ["entities-network-connections", entityIds],
    queryFn: async () => {
      const allConnections: EntityConnection[] = [];
      const seen = new Set<string>();

      const topEntities = (entitiesData?.items ?? [])
        .sort((a, b) => b.mention_count - a.mention_count)
        .slice(0, 50);

      const results = await Promise.all(
        topEntities.map((e) =>
          apiClient<{
            entity: EntityResponse;
            connections: EntityConnection[];
          }>({
            url: `/api/v1/entities/${e.id}/connections`,
            method: "GET",
            params: { limit: 20 },
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

  const toggleType = useCallback((type: string) => {
    setActiveTypes((prev) => {
      const next = new Set(prev);
      if (next.has(type)) {
        next.delete(type);
      } else {
        next.add(type);
      }
      return next;
    });
  }, []);

  const isLoading = entitiesLoading || connectionsLoading;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" asChild>
            <Link to="/entities">
              <ArrowLeft className="mr-2 h-4 w-4" />
              Back
            </Link>
          </Button>
          <div>
            <h1 className="text-2xl font-bold">Network Graph</h1>
            <p className="text-sm text-muted-foreground">
              {entitiesData
                ? `${entitiesData.items.length} entities, ${connectionsData?.length ?? 0} connections`
                : "Loading..."}
            </p>
          </div>
        </div>
      </div>

      <GraphControls
        activeTypes={activeTypes}
        onToggleType={toggleType}
        onZoomIn={() => graphRef.current?.zoomIn()}
        onZoomOut={() => graphRef.current?.zoomOut()}
        onFitView={() => graphRef.current?.fitView()}
      />

      {isLoading ? (
        <Skeleton
          className="w-full"
          style={{ height: "calc(100vh - 220px)" }}
        />
      ) : (
        <NetworkGraph
          ref={graphRef}
          entities={entitiesData?.items ?? []}
          connections={connectionsData ?? []}
          activeTypes={activeTypes}
        />
      )}
    </div>
  );
}
