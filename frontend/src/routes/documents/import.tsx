import { createFileRoute } from "@tanstack/react-router";
import { useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { Upload, Server, FileSpreadsheet } from "lucide-react";
import { apiClient } from "@/api/client";
import { useAuthStore } from "@/stores/auth-store";
import { useAppStore } from "@/stores/app-store";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { UploadWidget } from "@/components/documents/upload-widget";
import { IngestForm } from "@/components/datasets/ingest-form";
import { IngestProgress } from "@/components/datasets/ingest-progress";
import type { BulkImportStatusResponse, PaginatedResponse } from "@/types";
import type { EDRMImportResponse } from "@/api/generated/schemas";

export const Route = createFileRoute("/documents/import")({
  component: IngestPage,
});

function IngestPage() {
  const [mode, setMode] = useState<"upload" | "server" | "edrm">("upload");

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
          <div className="grid grid-cols-3 gap-3">
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
                  Directory, HuggingFace, Concordance
                </p>
              </div>
            </button>
            <button
              type="button"
              className={`flex items-center gap-3 rounded-lg border p-4 text-left transition-colors ${
                mode === "edrm"
                  ? "border-primary bg-primary/5"
                  : "border-border hover:bg-accent"
              }`}
              onClick={() => setMode("edrm")}
            >
              <FileSpreadsheet className="h-5 w-5 shrink-0" />
              <div>
                <p className="text-sm font-medium">EDRM / Load File</p>
                <p className="text-xs text-muted-foreground">
                  DAT, OPT, or EDRM XML
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

          {mode === "edrm" && (
            <div className="pt-2">
              <EDRMImportForm />
            </div>
          )}
        </CardContent>
      </Card>

      {/* EDRM XML Export */}
      <EDRMExportCard />

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

// ---------------------------------------------------------------------------
// EDRM Load File Import Form
// ---------------------------------------------------------------------------

function EDRMImportForm() {
  const matterId = useAppStore((s) => s.matterId);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [format, setFormat] = useState<string>("concordance_dat");

  const importMutation = useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData();
      formData.append("file", file);

      const token = useAuthStore.getState().accessToken;
      const res = await fetch(`/api/v1/edrm/import?format=${encodeURIComponent(format)}`, {
        method: "POST",
        headers: {
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
          ...(matterId ? { "X-Matter-ID": matterId } : {}),
        },
        body: formData,
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || `Import failed (${res.status})`);
      }

      return res.json() as Promise<EDRMImportResponse>;
    },
    onSuccess: (data) => {
      toast.success(data.message || `Imported ${data.record_count} records`);
      if (fileInputRef.current) fileInputRef.current.value = "";
    },
    onError: (err: Error) => {
      toast.error(err.message);
    },
  });

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="edrm-format">Load File Format</Label>
        <Select value={format} onValueChange={setFormat}>
          <SelectTrigger id="edrm-format">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="concordance_dat">Concordance DAT</SelectItem>
            <SelectItem value="opticon_opt">Opticon OPT</SelectItem>
            <SelectItem value="edrm_xml">EDRM XML</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <div className="space-y-2">
        <Label htmlFor="edrm-file">Load File</Label>
        <Input
          id="edrm-file"
          ref={fileInputRef}
          type="file"
          accept=".dat,.opt,.xml"
        />
      </div>
      <Button
        disabled={importMutation.isPending}
        onClick={() => {
          const file = fileInputRef.current?.files?.[0];
          if (!file) {
            toast.error("Please select a load file");
            return;
          }
          importMutation.mutate(file);
        }}
      >
        {importMutation.isPending ? "Importing..." : "Import Load File"}
      </Button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// EDRM XML Export Card
// ---------------------------------------------------------------------------

function EDRMExportCard() {
  const matterId = useAppStore((s) => s.matterId);

  const exportMutation = useMutation({
    mutationFn: async () => {
      const token = useAuthStore.getState().accessToken;
      const res = await fetch("/api/v1/edrm/export", {
        method: "GET",
        headers: {
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
          ...(matterId ? { "X-Matter-ID": matterId } : {}),
        },
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || `Export failed (${res.status})`);
      }

      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `edrm_export_${matterId ?? "unknown"}.xml`;
      a.click();
      URL.revokeObjectURL(url);
    },
    onError: (err: Error) => {
      toast.error(err.message);
    },
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">EDRM XML Export</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground mb-4">
          Export all documents in this matter as an EDRM XML load file.
        </p>
        <Button
          variant="outline"
          disabled={exportMutation.isPending || !matterId}
          onClick={() => exportMutation.mutate()}
        >
          {exportMutation.isPending ? "Exporting..." : "Download EDRM XML"}
        </Button>
      </CardContent>
    </Card>
  );
}
