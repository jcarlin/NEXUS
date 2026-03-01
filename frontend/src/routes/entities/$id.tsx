import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { apiClient } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EntityHeader } from "@/components/entities/entity-header";
import { ConnectionsGraph } from "@/components/entities/connections-graph";
import { DocumentMentions } from "@/components/entities/document-mentions";
import { EntityTimeline } from "@/components/entities/entity-timeline";
import type { EntityResponse, EntityConnection } from "@/types";

export const Route = createFileRoute("/entities/$id")({
  component: EntityDetailPage,
});

interface ConnectionsResponse {
  entity: EntityResponse;
  connections: EntityConnection[];
}

function EntityDetailPage() {
  const { id } = Route.useParams();

  const { data, isLoading, error } = useQuery({
    queryKey: ["entity-connections", id],
    queryFn: () =>
      apiClient<ConnectionsResponse>({
        url: `/api/v1/entities/${id}/connections`,
        method: "GET",
        params: { limit: 50 },
      }),
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

      <EntityHeader entity={data.entity} />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <ConnectionsGraph
          entity={data.entity}
          connections={data.connections}
        />
        <EntityTimeline entityId={id} />
      </div>

      <DocumentMentions entityName={data.entity.name} />
    </div>
  );
}
