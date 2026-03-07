import { useQuery } from "@tanstack/react-query";
import { Download } from "lucide-react";
import { apiClient } from "@/api/client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { Pagination } from "@/components/ui/pagination";
import type { ExportJob } from "@/routes/review/exports";

interface Props {
  data: ExportJob[];
  loading: boolean;
  total: number;
  offset: number;
  limit: number;
  onOffsetChange: (offset: number) => void;
}

const statusColors: Record<string, string> = {
  pending: "bg-yellow-500/15 text-yellow-700",
  processing: "bg-blue-500/15 text-blue-700",
  complete: "bg-green-500/15 text-green-700",
  failed: "bg-red-500/15 text-red-700",
};

function DownloadButton({ jobId }: { jobId: string }) {
  const { data } = useQuery({
    queryKey: ["export-download", jobId],
    queryFn: () =>
      apiClient<{ download_url: string }>({
        url: `/api/v1/exports/jobs/${jobId}/download`,
        method: "GET",
      }),
  });

  if (!data?.download_url) return null;

  return (
    <Button variant="outline" size="sm" asChild>
      <a href={data.download_url} target="_blank" rel="noreferrer">
        <Download className="mr-1.5 h-3.5 w-3.5" />
        Download
      </a>
    </Button>
  );
}

export function ExportJobList({
  data,
  loading,
  total,
  offset,
  limit,
  onOffsetChange,
}: Props) {
  if (loading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Type</TableHead>
            <TableHead>Format</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Created</TableHead>
            <TableHead>Completed</TableHead>
            <TableHead />
          </TableRow>
        </TableHeader>
        <TableBody>
          {data.length === 0 ? (
            <TableRow>
              <TableCell colSpan={6} className="text-center text-muted-foreground py-8">
                No export jobs yet. Create one to get started.
              </TableCell>
            </TableRow>
          ) : (
            data.map((job) => (
              <TableRow key={job.id}>
                <TableCell className="font-medium">{job.export_type}</TableCell>
                <TableCell>{job.export_format}</TableCell>
                <TableCell>
                  <Badge variant="secondary" className={statusColors[job.status] ?? ""}>
                    {job.status}
                  </Badge>
                </TableCell>
                <TableCell className="text-muted-foreground text-xs">
                  {new Date(job.created_at).toLocaleDateString()}
                </TableCell>
                <TableCell className="text-muted-foreground text-xs">
                  {job.completed_at
                    ? new Date(job.completed_at).toLocaleDateString()
                    : "—"}
                </TableCell>
                <TableCell>
                  {job.status === "complete" && <DownloadButton jobId={job.id} />}
                  {job.status === "failed" && job.error && (
                    <span className="text-xs text-destructive truncate max-w-[200px] block">
                      {job.error}
                    </span>
                  )}
                </TableCell>
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>

      {total > limit && (
        <Pagination
          total={total}
          offset={offset}
          limit={limit}
          onOffsetChange={onOffsetChange}
        />
      )}
    </div>
  );
}
