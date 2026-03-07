import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { Loader2, CheckCircle2, AlertCircle } from "lucide-react";
import { apiClient } from "@/api/client";
import { useAppStore } from "@/stores/app-store";
import { Progress } from "@/components/ui/progress";

interface CaseContext {
  status: string;
  claims?: unknown[];
  parties?: unknown[];
}

interface StepProcessingProps {
  onProcessingComplete: () => void;
}

export function StepProcessing({ onProcessingComplete }: StepProcessingProps) {
  const matterId = useAppStore((s) => s.matterId);

  const { data, error, isError } = useQuery({
    queryKey: ["case-context", matterId],
    queryFn: () =>
      apiClient<CaseContext>({
        url: `/api/v1/cases/${matterId}/context`,
        method: "GET",
      }),
    enabled: !!matterId,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status && status !== "processing") return false;
      return 3000;
    },
    retry: (failureCount, err) => {
      // Keep retrying on 404 — context may still be initializing
      if (err instanceof Error && err.message.includes("404")) return failureCount < 20;
      return failureCount < 3;
    },
    retryDelay: 3000,
  });

  const isComplete = data != null && data.status !== "processing";
  const isFailed = data?.status === "failed";

  useEffect(() => {
    if (isComplete && data && !isFailed) {
      onProcessingComplete();
    }
  }, [isComplete, data, isFailed, onProcessingComplete]);

  if (isFailed) {
    return (
      <div className="flex flex-col items-center gap-6 py-12">
        <AlertCircle className="h-12 w-12 text-destructive" />
        <div className="text-center">
          <h2 className="text-lg font-semibold">Processing Failed</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            The case setup agent encountered an error. Please try again.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center gap-6 py-12">
      {!isComplete ? (
        <>
          <Loader2 className="h-12 w-12 animate-spin text-primary" />
          <div className="text-center">
            <h2 className="text-lg font-semibold">Analyzing Document</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Parsing, extracting claims, parties, and timeline...
            </p>
          </div>
          <div className="w-full max-w-sm">
            <Progress value={data ? 50 : 10} />
            <p className="mt-2 text-center text-xs text-muted-foreground">
              {!data ? "Waiting for analysis to start..." : "Extracting case intelligence..."}
            </p>
          </div>
          {isError && error instanceof Error && error.message.includes("404") && (
            <p className="text-xs text-muted-foreground">
              Waiting for case context to initialize...
            </p>
          )}
        </>
      ) : (
        <>
          <CheckCircle2 className="h-12 w-12 text-green-500" />
          <div className="text-center">
            <h2 className="text-lg font-semibold">Analysis Complete</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Document analyzed. Continue to review and edit claims.
            </p>
          </div>
        </>
      )}
    </div>
  );
}
