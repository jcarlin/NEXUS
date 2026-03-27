import { Clock, RefreshCw, Server, Tag } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { formatDateTime } from "@/lib/utils";
import type { JobStatusResponse } from "@/types";

const CATEGORY_STYLES: Record<string, { bg: string; text: string }> = {
  TIMEOUT: { bg: "bg-red-100 dark:bg-red-900", text: "text-red-800 dark:text-red-200" },
  OOM: { bg: "bg-red-100 dark:bg-red-900", text: "text-red-800 dark:text-red-200" },
  PARSE_ERROR: { bg: "bg-blue-100 dark:bg-blue-900", text: "text-blue-800 dark:text-blue-200" },
  NETWORK: { bg: "bg-amber-100 dark:bg-amber-900", text: "text-amber-800 dark:text-amber-200" },
  LLM_API: { bg: "bg-amber-100 dark:bg-amber-900", text: "text-amber-800 dark:text-amber-200" },
  VALIDATION: { bg: "bg-purple-100 dark:bg-purple-900", text: "text-purple-800 dark:text-purple-200" },
  STORAGE: { bg: "bg-orange-100 dark:bg-orange-900", text: "text-orange-800 dark:text-orange-200" },
  UNKNOWN: { bg: "bg-muted", text: "text-muted-foreground" },
};

function categoryBadge(category: string | null | undefined) {
  const cat = category ?? "UNKNOWN";
  const style = CATEGORY_STYLES[cat] ?? CATEGORY_STYLES.UNKNOWN!;
  return (
    <Badge variant="secondary" className={`text-[10px] ${style?.bg} ${style?.text}`}>
      {cat}
    </Badge>
  );
}

function formatDuration(startedAt: string | null | undefined, completedAt: string | null | undefined): string {
  if (!startedAt || !completedAt) return "--";
  const ms = new Date(completedAt).getTime() - new Date(startedAt).getTime();
  if (ms < 1000) return `${ms}ms`;
  const secs = Math.round(ms / 1000);
  if (secs < 60) return `${secs}s`;
  const mins = Math.floor(secs / 60);
  const remainder = secs % 60;
  return remainder > 0 ? `${mins}m ${remainder}s` : `${mins}m`;
}

interface JobErrorPanelProps {
  job: JobStatusResponse;
}

export function JobErrorPanel({ job }: JobErrorPanelProps) {
  return (
    <div className="space-y-3 rounded-md border bg-muted/30 p-4">
      {/* Top row: category + stage + retry + worker */}
      <div className="flex flex-wrap items-center gap-3 text-xs">
        <div className="flex items-center gap-1.5">
          <Tag className="h-3 w-3 text-muted-foreground" />
          <span className="text-muted-foreground">Category:</span>
          {categoryBadge(job.error_category)}
        </div>

        <div className="flex items-center gap-1.5">
          <span className="text-muted-foreground">Stage:</span>
          <Badge variant="outline" className="text-[10px]">
            {job.progress?.stage ?? job.status}
          </Badge>
        </div>

        <div className="flex items-center gap-1.5">
          <RefreshCw className="h-3 w-3 text-muted-foreground" />
          <span className="text-muted-foreground">
            Attempt {(job.retry_count ?? 0) + 1} of 4
          </span>
        </div>

        {job.worker_hostname && (
          <div className="flex items-center gap-1.5">
            <Server className="h-3 w-3 text-muted-foreground" />
            <span className="font-mono text-muted-foreground">{job.worker_hostname}</span>
          </div>
        )}

        <div className="flex items-center gap-1.5">
          <Clock className="h-3 w-3 text-muted-foreground" />
          <span className="text-muted-foreground">
            Duration: {formatDuration(job.started_at, job.completed_at)}
          </span>
        </div>
      </div>

      {/* Timestamps */}
      <div className="flex flex-wrap gap-4 text-[11px] text-muted-foreground">
        <span>Created: {formatDateTime(job.created_at)}</span>
        {job.started_at && <span>Started: {formatDateTime(job.started_at)}</span>}
        {job.completed_at && <span>Failed: {formatDateTime(job.completed_at)}</span>}
      </div>

      {/* Error message */}
      {job.error && (
        <div className="rounded border bg-background p-3">
          <pre className="max-h-40 overflow-auto whitespace-pre-wrap text-xs font-mono text-destructive">
            {job.error}
          </pre>
        </div>
      )}
    </div>
  );
}
