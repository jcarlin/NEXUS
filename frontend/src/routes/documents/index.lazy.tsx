import { createLazyFileRoute, useNavigate } from "@tanstack/react-router";
import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import { useCallback, useState, useRef, useEffect } from "react";
import { Upload, AlertTriangle, ChevronDown, ChevronRight, RefreshCw, Loader2, FileUp, CheckCircle2, XCircle, Clock, X, RotateCcw } from "lucide-react";
import { toast } from "sonner";
import { apiClient } from "@/api/client";
import { useAppStore } from "@/stores/app-store";
import { useDebounce } from "@/hooks/use-debounce";
import { Button } from "@/components/ui/button";
import { Pagination } from "@/components/ui/pagination";
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { DocumentTable } from "@/components/documents/document-table";
import { DocumentFilters } from "@/components/documents/document-filters";
import { formatFileSize } from "@/lib/utils";
import type { DocumentResponse, PaginatedResponse } from "@/types";

export const Route = createLazyFileRoute("/documents/")({
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
  const [reindexingAll, setReindexingAll] = useState(false);

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
        url: "/api/v1/ingest/reindex",
        method: "POST",
        data: { doc_ids: [doc.doc_id] },
      });
      void queryClient.invalidateQueries({ queryKey: ["document-health"] });
      void queryClient.invalidateQueries({ queryKey: ["ingest-jobs"] });
    } finally {
      setReindexing((prev) => {
        const next = new Set(prev);
        next.delete(doc.doc_id);
        return next;
      });
    }
  };

  const handleReindexAll = async () => {
    const ids = unhealthy.map((d) => d.doc_id);
    setReindexingAll(true);
    try {
      // Send in batches of 500 (server max)
      for (let i = 0; i < ids.length; i += 500) {
        await apiClient({
          url: "/api/v1/ingest/reindex",
          method: "POST",
          data: { doc_ids: ids.slice(i, i + 500) },
        });
      }
      void queryClient.invalidateQueries({ queryKey: ["document-health"] });
      void queryClient.invalidateQueries({ queryKey: ["ingest-jobs"] });
    } finally {
      setReindexingAll(false);
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
        <Button
          size="sm"
          variant="outline"
          className="ml-auto h-6 px-2 text-xs"
          disabled={reindexingAll}
          onClick={handleReindexAll}
        >
          {reindexingAll ? (
            <>
              <Loader2 className="mr-1 h-3 w-3 animate-spin" />
              Re-indexing...
            </>
          ) : (
            <>
              <RefreshCw className="mr-1 h-3 w-3" />
              Re-index All ({unhealthyCount})
            </>
          )}
        </Button>
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

const STAGE_LABELS: Record<string, Record<string, string>> = {
  ingestion: {
    uploading: "Uploading",
    parsing: "Parsing document",
    chunking: "Chunking text",
    embedding: "Generating embeddings",
    extracting: "Extracting entities",
    indexing: "Indexing vectors",
  },
  entity_resolution: {
    loading_entities: "Loading entities",
    matching: "Matching",
    analyzing: "Analyzing",
    merging: "Merging duplicates",
  },
  reprocess_neo4j: {
    loading_chunks: "Loading chunks",
    indexing_entities: "Indexing entities",
  },
  analysis_sentiment: {
    loading_chunks: "Loading chunks",
    scoring: "Scoring sentiment",
    persisting: "Persisting results",
  },
  analysis_matter_scan: {
    querying_documents: "Querying documents",
    dispatching: "Dispatching tasks",
  },
  case_setup: {
    parsing: "Parsing document",
    extracting_claims: "Extracting claims",
    extracting_parties: "Extracting parties",
    extracting_terms: "Extracting terms",
    extracting_timeline: "Extracting timeline",
    populating_graph: "Populating graph",
  },
};

const STAGE_STEPS: Record<string, string[]> = {
  ingestion: ["parsing", "chunking", "embedding", "extracting", "indexing"],
  entity_resolution: ["loading_entities", "matching", "merging"],
  reprocess_neo4j: ["loading_chunks", "indexing_entities"],
  analysis_sentiment: ["loading_chunks", "scoring", "persisting"],
  analysis_matter_scan: ["querying_documents", "dispatching"],
  case_setup: ["parsing", "extracting_claims", "extracting_parties", "extracting_terms", "extracting_timeline", "populating_graph"],
};

const TASK_TYPE_LABELS: Record<string, string> = {
  ingestion: "Ingestion",
  entity_resolution: "Entity Resolution",
  reprocess_neo4j: "Neo4j Reindex",
  analysis_sentiment: "Sentiment Analysis",
  analysis_matter_scan: "Hot Doc Scan",
  case_setup: "Case Setup",
};

interface JobStatus {
  job_id: string;
  status: string;
  stage: string;
  filename: string | null;
  task_type: string;
  label: string | null;
  progress: Record<string, number>;
  error: string | null;
  created_at: string;
  updated_at: string;
  file_size_bytes?: number | null;
  page_count?: number | null;
}

const TERMINAL_STATUSES = new Set(["complete", "completed", "failed", "error"]);

function isTerminal(status: string): boolean {
  return TERMINAL_STATUSES.has(status);
}

function getJobDisplayName(job: JobStatus): string {
  return job.label ?? job.filename ?? TASK_TYPE_LABELS[job.task_type] ?? job.task_type;
}

function StatusBadge({ status }: { status: string }) {
  switch (status) {
    case "pending":
    case "queued":
      return (
        <Badge variant="secondary" className="text-[10px] px-1.5 py-0 gap-1">
          <Clock className="h-3 w-3" />
          Queued
        </Badge>
      );
    case "processing":
      return (
        <Badge variant="outline" className="text-[10px] px-1.5 py-0 gap-1 border-blue-500/50 text-blue-600 dark:text-blue-400">
          <Loader2 className="h-3 w-3 animate-spin" />
          Processing
        </Badge>
      );
    case "complete":
    case "completed":
      return (
        <Badge variant="secondary" className="text-[10px] px-1.5 py-0 gap-1 bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-400">
          <CheckCircle2 className="h-3 w-3" />
          Complete
        </Badge>
      );
    case "failed":
    case "error":
      return (
        <Badge variant="destructive" className="text-[10px] px-1.5 py-0 gap-1">
          <XCircle className="h-3 w-3" />
          Failed
        </Badge>
      );
    default:
      return (
        <Badge variant="outline" className="text-[10px] px-1.5 py-0">
          {status}
        </Badge>
      );
  }
}

function BackgroundTasks() {
  const matterId = useAppStore((s) => s.matterId);
  const queryClient = useQueryClient();
  const prevJobsRef = useRef<Map<string, string>>(new Map());

  const { data: jobs } = useQuery({
    queryKey: ["ingest-jobs", matterId],
    queryFn: () =>
      apiClient<PaginatedResponse<JobStatus>>({
        url: "/api/v1/jobs",
        method: "GET",
        params: { limit: 20 },
      }),
    enabled: !!matterId,
    refetchInterval: useCallback(
      (query: { state: { data: PaginatedResponse<JobStatus> | undefined } }) => {
        const items = query.state.data?.items ?? [];
        const hasActive = items.some((j) => !isTerminal(j.status));
        return hasActive ? 3000 : false;
      },
      [],
    ),
    gcTime: 5 * 60_000,
  });

  const cancelMutation = useMutation({
    mutationFn: (jobId: string) =>
      apiClient({ url: `/api/v1/jobs/${jobId}`, method: "DELETE" }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["ingest-jobs"] });
      toast.success("Job cancelled");
    },
    onError: () => {
      toast.error("Failed to cancel job");
    },
  });

  const retryMutation = useMutation({
    mutationFn: (jobId: string) =>
      apiClient({ url: `/api/v1/jobs/${jobId}/retry`, method: "POST" }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["ingest-jobs"] });
      toast.success("Job retried");
    },
    onError: () => {
      toast.error("Failed to retry job");
    },
  });

  const allJobs = jobs?.items ?? [];

  // Detect job completions/failures and show toasts + invalidate docs
  useEffect(() => {
    if (allJobs.length === 0) return;

    const prevMap = prevJobsRef.current;
    let shouldInvalidateDocs = false;

    for (const job of allJobs) {
      const prevStatus = prevMap.get(job.job_id);
      if (prevStatus && !isTerminal(prevStatus) && isTerminal(job.status)) {
        const name = getJobDisplayName(job);
        if (job.status === "complete" || job.status === "completed") {
          toast.success(`${name} completed successfully`);
          shouldInvalidateDocs = true;
        } else {
          toast.error(`${name} failed${job.error ? `: ${job.error}` : ""}`);
        }
      }
    }

    if (shouldInvalidateDocs) {
      void queryClient.invalidateQueries({ queryKey: ["documents"] });
      void queryClient.invalidateQueries({ queryKey: ["document-health"] });
    }

    // Update ref
    const nextMap = new Map<string, string>();
    for (const job of allJobs) {
      nextMap.set(job.job_id, job.status);
    }
    prevJobsRef.current = nextMap;
  }, [allJobs, queryClient]);

  const activeJobs = allJobs.filter((j) => !isTerminal(j.status));
  const terminalJobs = allJobs.filter((j) => isTerminal(j.status));
  const hasActive = activeJobs.length > 0;

  // Auto-collapse when no active jobs
  const [expanded, setExpanded] = useState(false);

  if (allJobs.length === 0) return null;

  const processingCount = allJobs.filter((j) => j.status === "processing").length;
  const completeCount = allJobs.filter((j) => j.status === "complete" || j.status === "completed").length;
  const failedCount = allJobs.filter((j) => j.status === "failed" || j.status === "error").length;
  const queuedCount = allJobs.filter((j) => j.status === "pending" || j.status === "queued").length;

  const summaryParts: string[] = [];
  if (processingCount > 0) summaryParts.push(`${processingCount} processing`);
  if (queuedCount > 0) summaryParts.push(`${queuedCount} queued`);
  if (completeCount > 0) summaryParts.push(`${completeCount} complete`);
  if (failedCount > 0) summaryParts.push(`${failedCount} failed`);

  // Show active jobs always; show terminal only when expanded
  const visibleJobs = hasActive ? activeJobs : (expanded ? allJobs : []);

  // Group visible jobs by task_type
  const grouped = new Map<string, JobStatus[]>();
  for (const job of visibleJobs) {
    const key = job.task_type ?? "ingestion";
    const list = grouped.get(key) ?? [];
    list.push(job);
    grouped.set(key, list);
  }

  return (
    <div className="rounded-lg border bg-card p-3 space-y-2">
      <div className="flex items-center gap-2 text-sm font-medium">
        {processingCount > 0 ? (
          <Loader2 className="h-4 w-4 animate-spin text-primary" />
        ) : (
          <FileUp className="h-4 w-4 text-muted-foreground" />
        )}
        <span>Background Tasks</span>
        {summaryParts.length > 0 && (
          <span className="text-xs font-normal text-muted-foreground">
            — {summaryParts.join(", ")}
          </span>
        )}
        {!hasActive && terminalJobs.length > 0 && (
          <button
            type="button"
            onClick={() => setExpanded(!expanded)}
            className="ml-auto text-xs text-muted-foreground hover:text-foreground transition-colors flex items-center gap-1"
          >
            {expanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
            {expanded ? "Hide" : "Show"} details
          </button>
        )}
      </div>
      {Array.from(grouped.entries()).map(([taskType, taskJobs]) => (
        <div key={taskType} className="space-y-1.5">
          {grouped.size > 1 && (
            <div className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider">
              {TASK_TYPE_LABELS[taskType] ?? taskType}
            </div>
          )}
          {taskJobs.map((job) => {
            const isProcessing = job.status === "processing";
            const steps = STAGE_STEPS[job.task_type] ?? STAGE_STEPS.ingestion!;
            const stepIdx = steps.indexOf(job.stage);
            const percent = stepIdx >= 0 ? Math.round(((stepIdx + 1) / steps.length) * 100) : 0;
            const stageMap = STAGE_LABELS[job.task_type] ?? STAGE_LABELS.ingestion!;
            const displayName = getJobDisplayName(job);

            return (
              <div key={job.job_id} className="space-y-1">
                <div className="flex items-center justify-between text-xs">
                  <div className="truncate max-w-[60%]">
                    <span className="text-muted-foreground" title={displayName}>
                      {displayName}
                    </span>
                    {isTerminal(job.status) && (job.page_count != null || job.file_size_bytes != null) && (
                      <span className="ml-1.5 text-[10px] text-muted-foreground/60">
                        {[
                          job.page_count != null ? `${job.page_count}p` : null,
                          job.file_size_bytes != null ? formatFileSize(job.file_size_bytes) : null,
                        ].filter(Boolean).join(" · ")}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-1.5">
                    {isProcessing && (
                      <Badge variant="outline" className="text-[10px] px-1.5 py-0">
                        {stageMap[job.stage] ?? job.stage}
                      </Badge>
                    )}
                    <StatusBadge status={job.status} />
                    {!isTerminal(job.status) && (
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
                    {job.status === "failed" && (
                      <button
                        type="button"
                        onClick={() => retryMutation.mutate(job.job_id)}
                        disabled={retryMutation.isPending}
                        className="rounded p-0.5 text-muted-foreground hover:text-primary hover:bg-primary/10 transition-colors"
                        title="Retry job"
                      >
                        <RotateCcw className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </div>
                </div>
                {isProcessing && <Progress value={percent} className="h-1" />}
              </div>
            );
          })}
        </div>
      ))}
    </div>
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
      <BackgroundTasks />

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
