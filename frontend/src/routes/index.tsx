import { useCallback } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { FileText, Users, Flame, Loader2, Network } from "lucide-react";
import { apiClient } from "@/api/client";
import { formatFileSize } from "@/lib/utils";
import { useAppStore } from "@/stores/app-store";
import { StatCard } from "@/components/dashboard/stat-card";
import { RecentActivity } from "@/components/dashboard/recent-activity";
import { PipelineStatus } from "@/components/dashboard/pipeline-status";
import { ServiceHealth } from "@/components/dashboard/service-health";
import { SystemMetrics } from "@/components/dashboard/system-metrics";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
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

  const { data: activeJobs, isLoading: jobsLoading } = useQuery({
    queryKey: ["active-jobs", matterId],
    queryFn: () =>
      apiClient<PaginatedResponse<{ id: string }>>({
        url: "/api/v1/jobs",
        method: "GET",
        params: { status: "processing", limit: 1 },
      }),
    enabled: !!matterId,
    refetchInterval: useCallback(
      (query: { state: { data: PaginatedResponse<{ id: string }> | undefined } }) => {
        const d = query.state.data;
        if (!d) return 10_000;
        return d.total > 0 ? 10_000 : false;
      },
      [],
    ),
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

  const { data: corpusStats, isLoading: statsLoading } = useQuery({
    queryKey: ["corpus-stats", matterId],
    queryFn: () =>
      apiClient<{ doc_count: number; total_pages: number; total_size_bytes: number }>({
        url: "/api/v1/documents/stats",
        method: "GET",
      }),
    enabled: !!matterId,
  });

  return (
    <div className="space-y-6 animate-page-in">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
        <p className="text-muted-foreground">Overview of your investigation workspace.</p>
      </div>

      <div className="flex gap-4">
        <ServiceHealth />
        <SystemMetrics />
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4 animate-stagger-in" data-tour="stat-cards">
        <StatCard
          title="Documents"
          value={docs?.total ?? 0}
          icon={FileText}
          loading={docsLoading || statsLoading}
          description={
            corpusStats
              ? `${formatFileSize(corpusStats.total_size_bytes)} · ${corpusStats.total_pages.toLocaleString()} pages`
              : "Total ingested"
          }
          href="/documents"
        />
        <StatCard
          title="Entities"
          value={graph?.node_counts?.Entity ?? 0}
          icon={Users}
          loading={graphLoading}
          description="In knowledge graph"
          href="/entities"
        />
        <StatCard
          title="Hot Docs"
          value={hotDocs?.total ?? 0}
          icon={Flame}
          loading={hotDocsLoading}
          description="Score >= 0.7"
          href="/review"
        />
        <StatCard
          title="Processing"
          value={activeJobs?.total ?? 0}
          icon={Loader2}
          loading={jobsLoading}
          description="Active pipeline jobs"
          href="/admin/pipeline"
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-3 animate-stagger-in" data-tour="recent-activity">
        <RecentActivity />
        <PipelineStatus />
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm font-medium">Knowledge Graph</CardTitle>
              <Link to="/entities/network" className="text-xs text-muted-foreground hover:text-foreground transition-colors">
                Explore
              </Link>
            </div>
          </CardHeader>
          <CardContent>
            {graphLoading ? (
              <div className="space-y-3">
                <Skeleton className="h-5 w-32" />
                <Skeleton className="h-5 w-24" />
              </div>
            ) : graph ? (
              <div className="space-y-4">
                <div className="flex gap-6">
                  <div>
                    <p className="text-2xl font-semibold tracking-tight tabular-nums">{(graph.node_counts?.Entity ?? 0).toLocaleString()}</p>
                    <p className="text-xs text-muted-foreground">Entities</p>
                  </div>
                  <div>
                    <p className="text-2xl font-semibold tracking-tight tabular-nums">{(graph.total_edges ?? 0).toLocaleString()}</p>
                    <p className="text-xs text-muted-foreground">Relationships</p>
                  </div>
                </div>
                <Link
                  to="/entities/network"
                  className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
                >
                  <Network className="h-4 w-4" />
                  View full graph visualization
                </Link>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">No graph data available</p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
