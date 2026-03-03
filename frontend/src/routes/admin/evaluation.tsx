import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
import { Separator } from "@/components/ui/separator";
import { QualityGates } from "@/components/admin/quality-gates";
import { DatasetBrowser } from "@/components/admin/dataset-browser";
import { RunHistory } from "@/components/admin/run-history";
import { RunComparison } from "@/components/admin/run-comparison";

export const Route = createFileRoute("/admin/evaluation")({
  component: EvaluationPage,
});

interface EvalRun {
  run_id: string;
  mode: string;
  created_at: string;
  status: string;
  metrics: Record<string, number>;
}

interface EvaluationResult {
  metrics: Record<string, number>;
  passed: boolean;
}

function EvaluationPage() {
  const { data: latestEval, isLoading: evalLoading, isError: evalError } = useQuery({
    queryKey: ["eval-latest"],
    queryFn: () =>
      apiClient<EvaluationResult>({
        url: "/api/v1/evaluation/latest",
        method: "GET",
      }),
    retry: (failureCount, error) => {
      // Don't retry 404s — no runs exist yet
      if (error instanceof Error && error.message.includes("404")) return false;
      return failureCount < 2;
    },
  });

  const { data: runsData, isLoading: runsLoading, isError: runsError } = useQuery({
    queryKey: ["eval-runs"],
    queryFn: () =>
      apiClient<{ items: EvalRun[] }>({
        url: "/api/v1/evaluation/runs",
        method: "GET",
      }),
    retry: (failureCount, error) => {
      if (error instanceof Error && error.message.includes("404")) return false;
      return failureCount < 2;
    },
  });

  const runs = runsError ? [] : (runsData?.items ?? []);

  return (
    <div className="space-y-8 animate-page-in">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Evaluation Pipeline</h1>
        <p className="text-muted-foreground">
          Manage evaluation datasets and run quality assessments.
        </p>
      </div>

      <section className="space-y-4">
        <h2 className="text-lg font-semibold">Quality Gates</h2>
        <QualityGates data={evalError ? undefined : latestEval} isLoading={evalLoading && !evalError} />
        {evalError && !evalLoading && (
          <p className="text-sm text-muted-foreground">No evaluation runs yet. Run an evaluation to see quality gates.</p>
        )}
      </section>

      <Separator />

      <section className="space-y-4">
        <h2 className="text-lg font-semibold">Datasets</h2>
        <DatasetBrowser />
      </section>

      <Separator />

      <section className="space-y-4">
        <h2 className="text-lg font-semibold">Run History</h2>
        <RunHistory data={runs} isLoading={runsLoading} />
      </section>

      {runs.length >= 2 && (
        <>
          <Separator />
          <section className="space-y-4">
            <h2 className="text-lg font-semibold">Run Comparison</h2>
            <RunComparison runs={runs} />
          </section>
        </>
      )}
    </div>
  );
}
