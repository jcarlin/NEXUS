import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { apiClient } from "@/api/client";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { UploadWidget } from "@/components/documents/upload-widget";

export const Route = createFileRoute("/documents/import")({
  component: ImportPage,
});

interface DryRunResponse {
  estimated_documents: number;
  estimated_chunks: number;
  estimated_duration_minutes: number;
  estimated_storage_mb: number;
  warnings: string[];
}

function ImportPage() {
  const [fileCount, setFileCount] = useState("");
  const [totalSize, setTotalSize] = useState("");

  const dryRun = useMutation({
    mutationFn: (data: { source_type: string; file_count?: number; total_size_bytes?: number }) =>
      apiClient<DryRunResponse>({
        url: "/api/v1/ingest/import/dry-run",
        method: "POST",
        data,
      }),
  });

  function handleDryRun() {
    dryRun.mutate({
      source_type: "upload",
      file_count: fileCount ? parseInt(fileCount) : undefined,
      total_size_bytes: totalSize ? parseInt(totalSize) * 1024 * 1024 : undefined,
    });
  }

  return (
    <div className="space-y-6 max-w-4xl">
      <div>
        <h1 className="text-2xl font-bold">Import Documents</h1>
        <p className="text-muted-foreground">Upload or import documents into the case.</p>
      </div>

      <Tabs defaultValue="upload">
        <TabsList>
          <TabsTrigger value="upload">Upload Files</TabsTrigger>
          <TabsTrigger value="s3">S3 Bucket</TabsTrigger>
          <TabsTrigger value="estimate">Estimate</TabsTrigger>
        </TabsList>

        <TabsContent value="upload" className="mt-4">
          <UploadWidget
            onUploadComplete={(results) => {
              toast.success(`${results.length} file(s) uploaded successfully`);
            }}
          />
        </TabsContent>

        <TabsContent value="s3" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle>Import from S3 Bucket</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label>S3 Prefix</Label>
                <Input placeholder="s3://bucket/prefix/" />
              </div>
              <Button>Start Import</Button>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="estimate" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle>Dry Run Estimate</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>Number of files</Label>
                  <Input type="number" value={fileCount} onChange={(e) => setFileCount(e.target.value)} placeholder="100" />
                </div>
                <div className="space-y-2">
                  <Label>Total size (MB)</Label>
                  <Input type="number" value={totalSize} onChange={(e) => setTotalSize(e.target.value)} placeholder="500" />
                </div>
              </div>
              <Button onClick={handleDryRun} disabled={dryRun.isPending}>
                {dryRun.isPending ? "Estimating..." : "Run Estimate"}
              </Button>

              {dryRun.data && (
                <div className="mt-4 rounded-md border p-4 space-y-2 text-sm">
                  <p>Documents: <strong>{dryRun.data.estimated_documents}</strong></p>
                  <p>Chunks: <strong>{dryRun.data.estimated_chunks}</strong></p>
                  <p>Duration: <strong>{dryRun.data.estimated_duration_minutes} min</strong></p>
                  <p>Storage: <strong>{dryRun.data.estimated_storage_mb} MB</strong></p>
                  {dryRun.data.warnings.map((w, i) => (
                    <p key={i} className="text-yellow-500 text-xs">{w}</p>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
