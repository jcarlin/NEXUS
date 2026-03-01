import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { FileText, Users, Flame, Loader2 } from "lucide-react";
import { apiClient } from "@/api/client";
import { StatCard } from "@/components/dashboard/stat-card";
import { RecentActivity } from "@/components/dashboard/recent-activity";
import { PipelineStatus } from "@/components/dashboard/pipeline-status";
import { GraphOverview } from "@/components/dashboard/graph-overview";
import type { PaginatedResponse, DocumentResponse, GraphStats } from "@/types";

export const Route = createFileRoute("/")({
  component: DashboardPage,
});

function DashboardPage() {
  const { data: docs, isLoading: docsLoading } = useQuery({
    queryKey: ["doc-count"],
    queryFn: () =>
      apiClient<PaginatedResponse<DocumentResponse>>({
        url: "/api/v1/documents",
        method: "GET",
        params: { limit: 1 },
      }),
  });

  const { data: graph, isLoading: graphLoading } = useQuery({
    queryKey: ["graph-stats-summary"],
    queryFn: () => apiClient<GraphStats>({ url: "/api/v1/graph/stats", method: "GET" }),
  });

  const { data: hotDocs, isLoading: hotDocsLoading } = useQuery({
    queryKey: ["hot-doc-count"],
    queryFn: () =>
      apiClient<PaginatedResponse<DocumentResponse>>({
        url: "/api/v1/documents",
        method: "GET",
        params: { limit: 1, hot_doc_score_min: 0.7 },
      }),
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <p className="text-muted-foreground">Overview of your investigation workspace.</p>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="Documents"
          value={docs?.total ?? 0}
          icon={FileText}
          loading={docsLoading}
          description="Total ingested"
        />
        <StatCard
          title="Entities"
          value={graph?.node_count ?? 0}
          icon={Users}
          loading={graphLoading}
          description="In knowledge graph"
        />
        <StatCard
          title="Hot Docs"
          value={hotDocs?.total ?? 0}
          icon={Flame}
          loading={hotDocsLoading}
          description="Score >= 0.7"
        />
        <StatCard
          title="Processing"
          value="—"
          icon={Loader2}
          loading={false}
          description="Active pipeline jobs"
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <RecentActivity />
        <PipelineStatus />
        <GraphOverview />
      </div>
    </div>
  );
}
