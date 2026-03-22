import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import type { BulkImportStatusResponse, PaginatedResponse } from "@/types";

interface IngestProgressProps {
  datasetId?: string | null;
}

const STATUS_VARIANT: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
  processing: "default",
  complete: "secondary",
  failed: "destructive",
};

export function IngestProgress({ datasetId }: IngestProgressProps) {
  const { data: jobs } = useQuery({
    queryKey: datasetId
      ? ["datasets", datasetId, "ingest", "status"]
      : ["bulk-imports"],
    queryFn: async () => {
      if (datasetId) {
        return apiClient<BulkImportStatusResponse[]>({
          url: `/api/v1/datasets/${datasetId}/ingest/status`,
          method: "GET",
        });
      }
      const paginated = await apiClient<PaginatedResponse<BulkImportStatusResponse>>({
        url: `/api/v1/bulk-imports`,
        method: "GET",
      });
      return paginated.items;
    },
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data) return 5000;
      const hasActive = data.some(
        (j) =>
          j.status === "processing" ||
          (j.total_documents > 0 &&
            j.processed_documents + j.failed_documents + j.skipped_documents <
              j.total_documents),
      );
      return hasActive ? 5000 : false;
    },
  });

  if (!jobs || jobs.length === 0) return null;

  // Show only recent jobs (last 5)
  const recentJobs = jobs.slice(0, 5);

  return (
    <div className="border-b px-4 py-2 space-y-2">
      {recentJobs.map((job) => {
        const processed =
          job.processed_documents + job.failed_documents + job.skipped_documents;
        const percent =
          job.total_documents > 0
            ? Math.round((processed / job.total_documents) * 100)
            : 0;

        return (
          <div key={job.id} className="space-y-1">
            <div className="flex items-center justify-between text-xs">
              <span className="text-muted-foreground truncate max-w-[60%]">
                {job.adapter_type}: {job.source_path?.split("/").pop()}
              </span>
              <div className="flex items-center gap-2">
                <span className="text-muted-foreground">
                  {processed}/{job.total_documents}
                </span>
                <Badge
                  variant={STATUS_VARIANT[job.status] ?? "outline"}
                  className="text-[10px] px-1.5 py-0"
                >
                  {job.status}
                </Badge>
              </div>
            </div>
            {(job.status === "processing" ||
              (job.total_documents > 0 && processed < job.total_documents)) && (
              <Progress value={percent} className="h-1.5" />
            )}
            {job.error && (
              <p className="text-[10px] text-destructive truncate">
                {job.error}
              </p>
            )}
          </div>
        );
      })}
    </div>
  );
}
