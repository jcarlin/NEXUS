import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Upload, AlertTriangle, ChevronDown, ChevronRight, RefreshCw } from "lucide-react";
import { apiClient } from "@/api/client";
import { useAppStore } from "@/stores/app-store";
import { useDebounce } from "@/hooks/use-debounce";
import { Button } from "@/components/ui/button";
import { Pagination } from "@/components/ui/pagination";
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert";
import { DocumentTable } from "@/components/documents/document-table";
import { DocumentFilters } from "@/components/documents/document-filters";
import type { DocumentResponse, PaginatedResponse } from "@/types";

export const Route = createFileRoute("/documents/")({
  component: DocumentsPage,
});

interface HealthItem {
  doc_id: string;
  filename: string;
  expected_chunks: number;
  indexed_chunks: number;
  status: "healthy" | "missing" | "partial";
}

interface HealthResponse {
  total: number;
  healthy: number;
  missing: number;
  partial: number;
  documents: HealthItem[];
}

function HealthBanner() {
  const matterId = useAppStore((s) => s.matterId);
  const queryClient = useQueryClient();
  const [expanded, setExpanded] = useState(false);
  const [reindexing, setReindexing] = useState<Set<string>>(new Set());

  const { data: health } = useQuery({
    queryKey: ["document-health", matterId],
    queryFn: () =>
      apiClient<HealthResponse>({
        url: "/api/v1/documents/health",
        method: "GET",
      }),
    enabled: !!matterId,
    staleTime: 60_000,
    retry: false,
  });

  if (!health || (health.missing === 0 && health.partial === 0)) return null;

  const unhealthy = health.documents.filter((d) => d.status !== "healthy");
  const unhealthyCount = health.missing + health.partial;

  const handleReindex = async (doc: HealthItem) => {
    setReindexing((prev) => new Set(prev).add(doc.doc_id));
    try {
      await apiClient({
        url: "/api/v1/ingest/process-uploaded",
        method: "POST",
        data: { files: [{ object_key: `reindex/${doc.doc_id}`, filename: doc.filename }] },
      });
      void queryClient.invalidateQueries({ queryKey: ["document-health"] });
    } finally {
      setReindexing((prev) => {
        const next = new Set(prev);
        next.delete(doc.doc_id);
        return next;
      });
    }
  };

  return (
    <Alert variant="destructive" className="border-amber-500/50 text-amber-700 dark:text-amber-400 [&>svg]:text-amber-600">
      <AlertTriangle className="h-4 w-4" />
      <AlertTitle className="flex items-center gap-2">
        {unhealthyCount} document{unhealthyCount !== 1 ? "s" : ""} need re-indexing
        <button
          type="button"
          onClick={() => setExpanded(!expanded)}
          className="ml-1 inline-flex items-center text-xs underline underline-offset-2 hover:no-underline"
        >
          {expanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
          {expanded ? "Hide" : "Show"}
        </button>
      </AlertTitle>
      {expanded && (
        <AlertDescription>
          <div className="mt-2 space-y-1">
            {unhealthy.map((doc) => (
              <div key={doc.doc_id} className="flex items-center justify-between gap-2 text-xs">
                <span className="truncate flex-1" title={doc.filename}>
                  {doc.filename}
                  <span className="ml-1 text-muted-foreground">
                    ({doc.indexed_chunks}/{doc.expected_chunks} chunks)
                  </span>
                </span>
                <span className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium ${
                  doc.status === "missing"
                    ? "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-400"
                    : "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-400"
                }`}>
                  {doc.status}
                </span>
                <Button
                  size="sm"
                  variant="outline"
                  className="h-6 px-2 text-[10px]"
                  disabled={reindexing.has(doc.doc_id)}
                  onClick={() => handleReindex(doc)}
                >
                  {reindexing.has(doc.doc_id) ? (
                    <RefreshCw className="mr-1 h-3 w-3 animate-spin" />
                  ) : (
                    <RefreshCw className="mr-1 h-3 w-3" />
                  )}
                  Re-index
                </Button>
              </div>
            ))}
          </div>
        </AlertDescription>
      )}
    </Alert>
  );
}

function DocumentsPage() {
  const navigate = useNavigate();
  const matterId = useAppStore((s) => s.matterId);
  const datasetId = useAppStore((s) => s.datasetId);
  const [search, setSearch] = useState("");
  const debouncedSearch = useDebounce(search, 300);
  const [fileExtension, setFileExtension] = useState("all");
  const [offset, setOffset] = useState(0);
  const limit = 50;

  const { data, isLoading } = useQuery({
    queryKey: ["documents", matterId, debouncedSearch, fileExtension, offset, datasetId],
    queryFn: () =>
      apiClient<PaginatedResponse<DocumentResponse>>({
        url: "/api/v1/documents",
        method: "GET",
        params: {
          q: debouncedSearch || undefined,
          file_extension: fileExtension !== "all" ? fileExtension : undefined,
          dataset_id: datasetId || undefined,
          offset,
          limit,
        },
      }),
    enabled: !!matterId,
  });

  return (
    <div className="space-y-4 animate-page-in">
      <HealthBanner />

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Documents</h1>
          <p className="text-sm text-muted-foreground">
            {data ? `${data.total} documents` : "Loading..."}
          </p>
        </div>
        <Button onClick={() => navigate({ to: "/documents/import" })}>
          <Upload className="mr-2 h-4 w-4" />
          Import
        </Button>
      </div>

      <DocumentFilters
        search={search}
        onSearchChange={(v) => { setSearch(v); setOffset(0); }}
        fileExtension={fileExtension}
        onFileExtensionChange={(v) => { setFileExtension(v); setOffset(0); }}
      />

      <DocumentTable data={data?.items ?? []} loading={isLoading} />

      {data && <Pagination total={data.total} offset={offset} limit={limit} onOffsetChange={setOffset} />}
    </div>
  );
}
