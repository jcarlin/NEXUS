import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { apiClient } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { DiffViewer } from "@/components/documents/diff-viewer";

interface CompareSearchParams {
  left: string;
  right: string;
}

export const Route = createFileRoute("/documents/compare")({
  component: CompareDocumentsPage,
  validateSearch: (
    search: Record<string, unknown>,
  ): CompareSearchParams => ({
    left: typeof search.left === "string" ? search.left : "",
    right: typeof search.right === "string" ? search.right : "",
  }),
});

interface DiffBlock {
  op: "equal" | "insert" | "delete" | "replace";
  left_start: number | null;
  left_end: number | null;
  right_start: number | null;
  right_end: number | null;
  left_text: string;
  right_text: string;
}

interface DiffResponse {
  left_id: string;
  right_id: string;
  left_filename: string;
  right_filename: string;
  blocks: DiffBlock[];
  truncated: boolean;
}

function CompareDocumentsPage() {
  const { left, right } = Route.useSearch();

  const { data, isLoading, error } = useQuery({
    queryKey: ["document-compare", left, right],
    queryFn: () =>
      apiClient<DiffResponse>({
        url: "/api/v1/documents/compare",
        method: "GET",
        params: { left_id: left, right_id: right },
      }),
    enabled: !!left && !!right,
  });

  if (!left || !right) {
    return (
      <div className="space-y-4 p-6">
        <p className="text-muted-foreground">
          Select two documents to compare. Use the <code>left</code> and{" "}
          <code>right</code> query parameters with document IDs.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4 p-6">
      <div className="flex items-center gap-4">
        <Link to="/documents">
          <Button variant="ghost" size="sm">
            <ArrowLeft className="mr-1 h-4 w-4" />
            Documents
          </Button>
        </Link>
        <h1 className="text-xl font-semibold">Document Comparison</h1>
      </div>

      {isLoading && (
        <div className="space-y-4">
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-[600px] w-full" />
        </div>
      )}

      {error && (
        <div className="rounded-md border border-red-300 bg-red-50 p-4 text-sm text-red-800 dark:border-red-700 dark:bg-red-950 dark:text-red-200">
          Failed to load comparison: {(error as Error).message}
        </div>
      )}

      {data && (
        <DiffViewer
          blocks={data.blocks}
          leftFilename={data.left_filename}
          rightFilename={data.right_filename}
          truncated={data.truncated}
        />
      )}
    </div>
  );
}
