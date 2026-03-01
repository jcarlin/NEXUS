import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
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
  const { data, isLoading } = useQuery({
    queryKey: ["pipeline-jobs"],
    queryFn: () =>
      apiClient<PaginatedResponse<JobStatusResponse>>({
        url: "/api/v1/jobs",
        method: "GET",
        params: { limit: 5 },
      }),
    refetchInterval: 5_000,
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-medium">Pipeline Status</CardTitle>
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
                    <Badge variant={statusColor(job.status)} className="text-[10px]">
                      {job.status}
                    </Badge>
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
