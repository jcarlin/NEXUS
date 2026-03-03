import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { Upload, Server } from "lucide-react";
import { apiClient } from "@/api/client";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { UploadWidget } from "@/components/documents/upload-widget";
import { IngestForm } from "@/components/datasets/ingest-form";
import { IngestProgress } from "@/components/datasets/ingest-progress";
import type { BulkImportStatusResponse, PaginatedResponse } from "@/types";

export const Route = createFileRoute("/documents/import")({
  component: IngestPage,
});

function IngestPage() {
  const [mode, setMode] = useState<"upload" | "server">("upload");

  const { data: history } = useQuery({
    queryKey: ["bulk-imports-history"],
    queryFn: () =>
      apiClient<PaginatedResponse<BulkImportStatusResponse>>({
        url: "/api/v1/bulk-imports",
        method: "GET",
        params: { limit: 20 },
      }),
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data) return 10000;
      const hasActive = data.items.some((j) => j.status === "processing");
      return hasActive ? 5000 : false;
    },
  });

  return (
    <div className="space-y-6 max-w-4xl mx-auto p-6 animate-page-in">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Ingest Documents</h1>
        <p className="text-muted-foreground">
          Upload files or ingest from a server-side source.
        </p>
      </div>

      {/* Active ingest progress */}
      <IngestProgress />

      {/* Ingest mode selector */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Ingest Mode</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <button
              type="button"
              className={`flex items-center gap-3 rounded-lg border p-4 text-left transition-colors ${
                mode === "upload"
                  ? "border-primary bg-primary/5"
                  : "border-border hover:bg-accent"
              }`}
              onClick={() => setMode("upload")}
            >
              <Upload className="h-5 w-5 shrink-0" />
              <div>
                <p className="text-sm font-medium">Upload Files</p>
                <p className="text-xs text-muted-foreground">
                  Upload from your computer
                </p>
              </div>
            </button>
            <button
              type="button"
              className={`flex items-center gap-3 rounded-lg border p-4 text-left transition-colors ${
                mode === "server"
                  ? "border-primary bg-primary/5"
                  : "border-border hover:bg-accent"
              }`}
              onClick={() => setMode("server")}
            >
              <Server className="h-5 w-5 shrink-0" />
              <div>
                <p className="text-sm font-medium">Server Source</p>
                <p className="text-xs text-muted-foreground">
                  Directory, HuggingFace, EDRM, Concordance
                </p>
              </div>
            </button>
          </div>

          {mode === "upload" && (
            <div className="pt-2">
              <UploadWidget
                onUploadComplete={(results) => {
                  toast.success(
                    `${results.length} file(s) uploaded and queued for ingestion`,
                  );
                }}
              />
            </div>
          )}

          {mode === "server" && (
            <div className="pt-2">
              <IngestForm datasetId={null} />
            </div>
          )}
        </CardContent>
      </Card>

      {/* Ingest history */}
      {history && history.items.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Ingest History</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-xs text-muted-foreground">
                    <th className="pb-2 pr-4 font-medium">Date</th>
                    <th className="pb-2 pr-4 font-medium">Source</th>
                    <th className="pb-2 pr-4 font-medium text-right">Docs</th>
                    <th className="pb-2 pr-4 font-medium text-right">
                      Skipped
                    </th>
                    <th className="pb-2 pr-4 font-medium text-right">
                      Failed
                    </th>
                    <th className="pb-2 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {history.items.map((job) => (
                    <tr key={job.id}>
                      <td className="py-2 pr-4 text-muted-foreground whitespace-nowrap">
                        {new Date(job.created_at).toLocaleDateString()}
                      </td>
                      <td className="py-2 pr-4 truncate max-w-[200px]">
                        {job.adapter_type ?? "upload"}
                        {job.source_path && (
                          <span className="text-muted-foreground">
                            : {job.source_path.split("/").pop()}
                          </span>
                        )}
                      </td>
                      <td className="py-2 pr-4 text-right tabular-nums">
                        {job.processed_documents}/{job.total_documents}
                      </td>
                      <td className="py-2 pr-4 text-right tabular-nums">
                        {job.skipped_documents}
                      </td>
                      <td className="py-2 pr-4 text-right tabular-nums">
                        {job.failed_documents}
                      </td>
                      <td className="py-2">
                        <Badge
                          variant={
                            job.status === "complete"
                              ? "secondary"
                              : job.status === "failed"
                                ? "destructive"
                                : job.status === "processing"
                                  ? "default"
                                  : "outline"
                          }
                          className="text-[10px] px-1.5 py-0"
                        >
                          {job.status}
                        </Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
