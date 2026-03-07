import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
import { useAppStore } from "@/stores/app-store";
import { useFeatureFlag } from "@/hooks/use-feature-flags";
import { HotDocTable } from "@/components/review/hot-doc-table";
import { FeatureDisabledBanner } from "@/components/ui/feature-disabled-banner";
import type { DocumentDetail, PaginatedResponse } from "@/types";

export const Route = createFileRoute("/review/hot-docs")({
  component: HotDocsPage,
});

function HotDocsPage() {
  const matterId = useAppStore((s) => s.matterId);
  const hotDocEnabled = useFeatureFlag("hot_doc_detection");

  const { data, isLoading } = useQuery({
    queryKey: ["hot-docs", matterId],
    queryFn: () =>
      apiClient<PaginatedResponse<DocumentDetail>>({
        url: "/api/v1/documents",
        method: "GET",
        params: {
          hot_doc_score_min: 0.7,
          limit: 50,
        },
      }),
    enabled: !!matterId,
  });

  return (
    <div className="space-y-4 animate-page-in">
      {!hotDocEnabled && (
        <FeatureDisabledBanner featureName="Hot Document Detection" />
      )}
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Hot Documents</h1>
        <p className="text-sm text-muted-foreground">
          {data ? `${data.total} documents with hot score >= 0.7` : "Loading..."}
        </p>
      </div>

      <HotDocTable data={data?.items ?? []} loading={isLoading} />
    </div>
  );
}
