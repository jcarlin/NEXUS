import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { toast } from "sonner";
import { X } from "lucide-react";
import { apiClient } from "@/api/client";
import { useAppStore } from "@/stores/app-store";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { PaginatedResponse, JobStatusResponse } from "@/types";

function statusColor(status: string) {
  switch (status) {
    case "completed": return "default";
    case "failed": return "destructive";
    case "processing": return "secondary";
    default: return "outline";
  }
}

function jobProgress(job: JobStatusResponse): number {
  if (job.status === "completed") return 100;
  if (job.status === "failed") return 0;
  const p = job.progress;
  if (!p) return 0;
  const stages = ["parsing", "chunking", "embedding", "extracting", "indexing", "completed"];
  const idx = stages.indexOf(p.stage);
  return idx >= 0 ? Math.round(((idx + 1) / stages.length) * 100) : 10;
}

export function PipelineStatus() {
  const matterId = useAppStore((s) => s.matterId);
  const queryClient = useQueryClient();
  const cancelMutation = useMutation({
    mutationFn: (jobId: string) =>
      apiClient({ url: `/api/v1/jobs/${jobId}`, method: "DELETE" }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["pipeline-jobs"] });
      toast.success("Job cancelled");
    },
    onError: () => {
      toast.error("Failed to cancel job");
    },
  });

  const { data, isLoading } = useQuery({
    queryKey: ["pipeline-jobs", matterId],
    queryFn: () =>
      apiClient<PaginatedResponse<JobStatusResponse>>({
        url: "/api/v1/jobs",
        method: "GET",
        params: { limit: 5 },
      }),
    enabled: !!matterId,
    refetchInterval: 5_000,
  });

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium">Pipeline Status</CardTitle>
          <Link to="/documents/import" className="text-xs text-muted-foreground hover:text-foreground transition-colors">
            View all
          </Link>
        </div>
      </CardHeader>
      <CardContent>
        <ScrollArea className="h-[280px]">
          {isLoading ? (
            <div className="space-y-3">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-14 w-full" />
              ))}
            </div>
          ) : (
            <div className="space-y-3">
              {data?.items.map((job) => (
                <div key={job.job_id} className="space-y-1 rounded-md border p-3">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium truncate max-w-[200px]">{job.filename ?? job.job_id.slice(0, 8)}</span>
                    <div className="flex items-center gap-1.5">
                      <Badge variant={statusColor(job.status)} className="text-[10px]">
                        {job.status}
                      </Badge>
                      {job.status === "processing" && (
                        <button
                          type="button"
                          onClick={() => cancelMutation.mutate(job.job_id)}
                          disabled={cancelMutation.isPending}
                          className="rounded p-0.5 text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors"
                          title="Cancel job"
                        >
                          <X className="h-3.5 w-3.5" />
                        </button>
                      )}
                    </div>
                  </div>
                  {job.status === "processing" && (
                    <div className="space-y-1">
                      <Progress value={jobProgress(job)} className="h-1.5" />
                      <p className="text-[10px] text-muted-foreground">{job.progress?.stage}</p>
                    </div>
                  )}
                </div>
              ))}
              {data?.items.length === 0 && (
                <p className="text-center text-sm text-muted-foreground py-8">No active jobs</p>
              )}
            </div>
          )}
        </ScrollArea>
      </CardContent>
    </Card>
  );
}
