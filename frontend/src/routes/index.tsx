import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { FileText, Users, Flame, Loader2 } from "lucide-react";
import { apiClient } from "@/api/client";
import { useAppStore } from "@/stores/app-store";
import { StatCard } from "@/components/dashboard/stat-card";
import { RecentActivity } from "@/components/dashboard/recent-activity";
import { PipelineStatus } from "@/components/dashboard/pipeline-status";
import { GraphOverview } from "@/components/dashboard/graph-overview";
import type { PaginatedResponse, DocumentResponse, GraphStats } from "@/types";

export const Route = createFileRoute("/")({
  component: DashboardPage,
});

function DashboardPage() {
  const matterId = useAppStore((s) => s.matterId);

  const { data: docs, isLoading: docsLoading } = useQuery({
    queryKey: ["doc-count", matterId],
    queryFn: () =>
      apiClient<PaginatedResponse<DocumentResponse>>({
        url: "/api/v1/documents",
        method: "GET",
        params: { limit: 1 },
      }),
    enabled: !!matterId,
  });

  const { data: graph, isLoading: graphLoading } = useQuery({
    queryKey: ["graph-stats-summary", matterId],
    queryFn: () => apiClient<GraphStats>({ url: "/api/v1/graph/stats", method: "GET" }),
    enabled: !!matterId,
  });

  const { data: hotDocs, isLoading: hotDocsLoading } = useQuery({
    queryKey: ["hot-doc-count", matterId],
    queryFn: () =>
      apiClient<PaginatedResponse<DocumentResponse>>({
        url: "/api/v1/documents",
        method: "GET",
        params: { limit: 1, hot_doc_score_min: 0.7 },
      }),
    enabled: !!matterId,
  });

  return (
    <div className="space-y-6 animate-page-in">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
        <p className="text-muted-foreground">Overview of your investigation workspace.</p>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4 animate-stagger-in">
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

      <div className="grid gap-4 lg:grid-cols-3 animate-stagger-in">
        <RecentActivity />
        <PipelineStatus />
        <GraphOverview />
      </div>
    </div>
  );
}
