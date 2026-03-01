import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { Loader2, CheckCircle2 } from "lucide-react";
import { apiClient } from "@/api/client";
import { useAppStore } from "@/stores/app-store";
import { Progress } from "@/components/ui/progress";

interface CaseContext {
  status: string;
  documents_processed?: number;
  documents_total?: number;
}

interface StepProcessingProps {
  onProcessingComplete: () => void;
}

export function StepProcessing({ onProcessingComplete }: StepProcessingProps) {
  const matterId = useAppStore((s) => s.matterId);

  const { data } = useQuery({
    queryKey: ["case-context", matterId],
    queryFn: () =>
      apiClient<CaseContext>({
        url: `/api/v1/cases/${matterId}/context`,
        method: "GET",
      }),
    enabled: !!matterId,
    refetchInterval: (query) => {
      if (query.state.data?.status !== "processing") return false;
      return 3000;
    },
  });

  const isComplete = data?.status !== "processing";
  const progress =
    data?.documents_total && data.documents_total > 0
      ? Math.round(
          ((data.documents_processed ?? 0) / data.documents_total) * 100,
        )
      : 0;

  useEffect(() => {
    if (isComplete && data) {
      onProcessingComplete();
    }
  }, [isComplete, data, onProcessingComplete]);

  return (
    <div className="flex flex-col items-center gap-6 py-12">
      {!isComplete ? (
        <>
          <Loader2 className="h-12 w-12 animate-spin text-primary" />
          <div className="text-center">
            <h2 className="text-lg font-semibold">Processing Documents</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Parsing, chunking, and extracting entities...
            </p>
          </div>
          <div className="w-full max-w-sm">
            <Progress value={progress} />
            <p className="mt-2 text-center text-xs text-muted-foreground">
              {data?.documents_processed ?? 0} / {data?.documents_total ?? "?"}{" "}
              documents
            </p>
          </div>
        </>
      ) : (
        <>
          <CheckCircle2 className="h-12 w-12 text-green-500" />
          <div className="text-center">
            <h2 className="text-lg font-semibold">Processing Complete</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              All documents have been processed. Continue to configure claims.
            </p>
          </div>
        </>
      )}
    </div>
  );
}
