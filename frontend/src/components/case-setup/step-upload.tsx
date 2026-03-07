import { useState, useRef } from "react";
import { Upload, FileText, Loader2 } from "lucide-react";
import { useMutation } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { useAppStore } from "@/stores/app-store";

interface CaseSetupResult {
  job_id: string;
  case_context_id: string;
  status: string;
  created_at: string;
}

interface StepUploadProps {
  onUploadComplete: (result: CaseSetupResult) => void;
}

export function StepUpload({ onUploadComplete }: StepUploadProps) {
  const matterId = useAppStore((s) => s.matterId);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const uploadMutation = useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData();
      formData.append("file", file);

      const token = localStorage.getItem("access_token");
      const res = await fetch(`/api/v1/cases/${matterId}/setup`, {
        method: "POST",
        headers: {
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
          "X-Matter-ID": matterId ?? "",
        },
        body: formData,
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || `Upload failed (${res.status})`);
      }

      return res.json() as Promise<CaseSetupResult>;
    },
    onSuccess: (data) => {
      onUploadComplete(data);
    },
  });

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0] ?? null;
    setSelectedFile(file);
  }

  function handleUpload() {
    if (selectedFile) {
      uploadMutation.mutate(selectedFile);
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold">Upload Anchor Document</h2>
        <p className="text-sm text-muted-foreground">
          Upload the complaint or key filing that defines the case. It will be
          parsed and analyzed to extract claims, parties, and timeline.
        </p>
      </div>

      <div
        className="flex flex-col items-center gap-4 rounded-lg border-2 border-dashed p-8 cursor-pointer hover:border-primary/50 transition-colors"
        onClick={() => inputRef.current?.click()}
      >
        <input
          ref={inputRef}
          type="file"
          className="hidden"
          accept=".pdf,.docx,.doc,.txt,.html"
          onChange={handleFileChange}
        />

        {selectedFile ? (
          <>
            <FileText className="h-10 w-10 text-primary" />
            <div className="text-center">
              <p className="font-medium">{selectedFile.name}</p>
              <p className="text-xs text-muted-foreground">
                {(selectedFile.size / 1024).toFixed(0)} KB
              </p>
            </div>
          </>
        ) : (
          <>
            <Upload className="h-10 w-10 text-muted-foreground" />
            <div className="text-center">
              <p className="text-sm font-medium">Click to select a file</p>
              <p className="text-xs text-muted-foreground">
                PDF, DOCX, DOC, TXT, or HTML
              </p>
            </div>
          </>
        )}
      </div>

      {selectedFile && (
        <Button
          onClick={handleUpload}
          disabled={uploadMutation.isPending}
          className="w-full"
        >
          {uploadMutation.isPending ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              Uploading & Starting Analysis...
            </>
          ) : (
            "Upload & Start Case Setup"
          )}
        </Button>
      )}

      {uploadMutation.isError && (
        <div className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
          {uploadMutation.error.message}
        </div>
      )}
    </div>
  );
}
