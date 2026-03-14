import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useState, useCallback, useRef, useMemo } from "react";
import { ArrowLeft } from "lucide-react";
import { apiClient } from "@/api/client";
import { useAppStore } from "@/stores/app-store";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  NetworkGraph,
  type NetworkGraphHandle,
} from "@/components/entities/network-graph";
import { GraphControls } from "@/components/entities/graph-controls";
import { PathFinder } from "@/components/entities/path-finder";
import { CypherExplorer } from "@/components/entities/cypher-explorer";
import {
  RenameDialog,
  ChangeTypeDialog,
  MergeDialog,
  DeleteConfirmDialog,
} from "@/components/entities/entity-edit-dialogs";
import type {
  EntityResponse,
  EntityConnection,
  PaginatedResponse,
} from "@/types";

export const Route = createFileRoute("/entities/network")({
  component: NetworkGraphPage,
});

const DEFAULT_TYPES = new Set(["person", "organization", "location", "date", "monetary_amount"]);

interface ContextMenuState {
  x: number;
  y: number;
  entityName: string;
  entityType: string;
}

type DialogType = "rename" | "changeType" | "merge" | "delete" | null;

function NetworkGraphPage() {
  const matterId = useAppStore((s) => s.matterId);
  const [activeTypes, setActiveTypes] = useState<Set<string>>(
    () => new Set(DEFAULT_TYPES),
  );
  const graphRef = useRef<NetworkGraphHandle>(null);
  const [editMode, setEditMode] = useState(false);
  const [contextMenu, setContextMenu] = useState<ContextMenuState | null>(null);
  const [activeDialog, setActiveDialog] = useState<DialogType>(null);
  const [selectedEntity, setSelectedEntity] = useState<{ name: string; type: string }>({ name: "", type: "" });

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
  const entityIds = useMemo(
    () => entitiesData?.items.map((e) => e.id) ?? [],
    [entitiesData],
  );
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
            url: `/api/v1/entities/connections`,
            method: "GET",
            params: { name: e.id, limit: 20 },
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

  const handleNodeContextMenu = useCallback((event: MouseEvent, node: { name: string; type: string }) => {
    if (!editMode) return;
    event.preventDefault();
    setContextMenu({ x: event.clientX, y: event.clientY, entityName: node.name, entityType: node.type });
  }, [editMode]);

  const openDialog = useCallback((type: DialogType) => {
    if (contextMenu) {
      setSelectedEntity({ name: contextMenu.entityName, type: contextMenu.entityType });
    }
    setActiveDialog(type);
    setContextMenu(null);
  }, [contextMenu]);

  const isLoading = entitiesLoading || connectionsLoading;

  return (
    <div className="space-y-4 animate-page-in">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" asChild>
            <Link to="/entities">
              <ArrowLeft className="mr-2 h-4 w-4" />
              Back
            </Link>
          </Button>
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Network Graph</h1>
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
        editMode={editMode}
        onToggleEditMode={() => setEditMode((prev) => !prev)}
      />

      <PathFinder />

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
          onNodeContextMenu={handleNodeContextMenu}
        />
      )}

      <CypherExplorer />

      {/* Context menu for graph nodes */}
      {contextMenu && (
        <DropdownMenu open onOpenChange={() => setContextMenu(null)}>
          <DropdownMenuTrigger asChild>
            <div className="fixed" style={{ left: contextMenu.x, top: contextMenu.y, width: 1, height: 1 }} />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start">
            <DropdownMenuItem onClick={() => openDialog("rename")}>Rename</DropdownMenuItem>
            <DropdownMenuItem onClick={() => openDialog("changeType")}>Change Type</DropdownMenuItem>
            <DropdownMenuItem onClick={() => openDialog("merge")}>Merge With...</DropdownMenuItem>
            <DropdownMenuItem className="text-destructive" onClick={() => openDialog("delete")}>Delete</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      )}

      {/* Edit dialogs */}
      <RenameDialog
        open={activeDialog === "rename"}
        onOpenChange={(open) => !open && setActiveDialog(null)}
        entityName={selectedEntity.name}
      />
      <ChangeTypeDialog
        open={activeDialog === "changeType"}
        onOpenChange={(open) => !open && setActiveDialog(null)}
        entityName={selectedEntity.name}
        currentType={selectedEntity.type}
      />
      <MergeDialog
        open={activeDialog === "merge"}
        onOpenChange={(open) => !open && setActiveDialog(null)}
        entityName={selectedEntity.name}
      />
      <DeleteConfirmDialog
        open={activeDialog === "delete"}
        onOpenChange={(open) => !open && setActiveDialog(null)}
        entityName={selectedEntity.name}
      />
    </div>
  );
}
