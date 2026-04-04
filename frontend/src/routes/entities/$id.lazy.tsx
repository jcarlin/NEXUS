import { createLazyFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useState, useCallback, useMemo } from "react";
import { ArrowLeft, MoreHorizontal } from "lucide-react";
import { useViewState } from "@/hooks/use-view-state";
import { apiClient } from "@/api/client";
import { useAppStore } from "@/stores/app-store";
import { useAuthStore } from "@/stores/auth-store";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { EntityHeader } from "@/components/entities/entity-header";
import { ConnectionsGraph } from "@/components/entities/connections-graph";
import { GraphControls } from "@/components/entities/graph-controls";
import { DocumentMentions } from "@/components/entities/document-mentions";
import { EntityTimeline } from "@/components/entities/entity-timeline";
import { ReportingChain } from "@/components/entities/reporting-chain";
import {
  RenameDialog,
  ChangeTypeDialog,
  DeleteConfirmDialog,
} from "@/components/entities/entity-edit-dialogs";
import type { EntityResponse, EntityConnection } from "@/types";

export const Route = createLazyFileRoute("/entities/$id")({
  component: EntityDetailPage,
});

interface ConnectionsResponse {
  entity: EntityResponse;
  connections: EntityConnection[];
}

type EditDialog = "rename" | "changeType" | "delete" | null;

const DEFAULT_TYPES = new Set(["person", "organization", "location", "date", "monetary_amount"]);

function EntityDetailPage() {
  const { id } = Route.useParams();
  const matterId = useAppStore((s) => s.matterId);
  const user = useAuthStore((s) => s.user);
  const canEdit = user?.role === "admin" || user?.role === "attorney";
  const [activeDialog, setActiveDialog] = useState<EditDialog>(null);
  const [selectedConnection, setSelectedConnection] = useState<EntityConnection | null>(null);

  const [filterVS, setFilterVS] = useViewState("/entities/filters", {
    activeTypes: [...DEFAULT_TYPES],
  });
  const activeTypes = useMemo(() => new Set(filterVS.activeTypes), [filterVS.activeTypes]);
  const toggleType = useCallback((type: string) => {
    const current = new Set(filterVS.activeTypes);
    if (current.has(type)) current.delete(type);
    else current.add(type);
    setFilterVS({ activeTypes: [...current] });
  }, [filterVS.activeTypes, setFilterVS]);

  const { data, isLoading, error } = useQuery({
    queryKey: ["entity-connections", matterId, id],
    queryFn: () =>
      apiClient<ConnectionsResponse>({
        url: `/api/v1/entities/connections`,
        method: "GET",
        params: { name: id, limit: 200, entity_only: true },
      }),
    enabled: !!matterId,
  });

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-40 w-full" />
        <Skeleton className="h-[350px] w-full" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="space-y-4">
        <Button variant="ghost" size="sm" asChild>
          <Link to="/entities">
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back to Entities
          </Link>
        </Button>
        <p className="text-sm text-destructive">
          Failed to load entity details.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Button variant="ghost" size="sm" asChild>
        <Link to="/entities">
          <ArrowLeft className="mr-2 h-4 w-4" />
          Back to Entities
        </Link>
      </Button>

      <div className="flex items-center justify-between">
        <EntityHeader entity={data.entity} />
        {canEdit && (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="icon" className="h-8 w-8">
                <MoreHorizontal className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={() => setActiveDialog("rename")}>Rename</DropdownMenuItem>
              <DropdownMenuItem onClick={() => setActiveDialog("changeType")}>Change Type</DropdownMenuItem>
              <DropdownMenuItem className="text-destructive" onClick={() => setActiveDialog("delete")}>Delete</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        )}
      </div>

      <GraphControls
        activeTypes={activeTypes}
        onToggleType={toggleType}
      />

      {selectedConnection && (
        <div className="flex items-center gap-3 rounded-md border bg-muted/40 px-4 py-2.5 text-sm">
          <span className="font-medium">{selectedConnection.source}</span>
          <span className="text-muted-foreground">{selectedConnection.relationship_type.replace(/_/g, " ").toLowerCase()}</span>
          <span className="font-medium">{selectedConnection.target}</span>
          {selectedConnection.weight > 1 && (
            <span className="text-xs text-muted-foreground">({selectedConnection.weight}x)</span>
          )}
          {selectedConnection.context && (
            <span className="text-xs text-muted-foreground ml-2">— {selectedConnection.context}</span>
          )}
          <button
            onClick={() => setSelectedConnection(null)}
            className="ml-auto text-xs text-muted-foreground hover:text-foreground"
          >
            Clear
          </button>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <ConnectionsGraph
          entity={data.entity}
          connections={data.connections.filter(
            (c) => !c.target_type || activeTypes.has(c.target_type),
          )}
          selectedConnection={selectedConnection}
          onConnectionSelect={setSelectedConnection}
        />
        <EntityTimeline entityId={id} filterEntity={selectedConnection?.target ?? selectedConnection?.source} centralEntity={data.entity.name} />
      </div>

      <DocumentMentions entityName={data.entity.name} />

      {data.entity.type === "PERSON" && (
        <ReportingChain personName={data.entity.name} />
      )}

      {canEdit && (
        <>
          <RenameDialog
            open={activeDialog === "rename"}
            onOpenChange={(open) => !open && setActiveDialog(null)}
            entityName={data.entity.name}
          />
          <ChangeTypeDialog
            open={activeDialog === "changeType"}
            onOpenChange={(open) => !open && setActiveDialog(null)}
            entityName={data.entity.name}
            currentType={data.entity.type}
          />
          <DeleteConfirmDialog
            open={activeDialog === "delete"}
            onOpenChange={(open) => !open && setActiveDialog(null)}
            entityName={data.entity.name}
          />
        </>
      )}
    </div>
  );
}
