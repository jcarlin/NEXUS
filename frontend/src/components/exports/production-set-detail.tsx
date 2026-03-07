import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Trash2 } from "lucide-react";
import { apiClient } from "@/api/client";
import { useAppStore } from "@/stores/app-store";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { Pagination } from "@/components/ui/pagination";
import type { PaginatedResponse } from "@/types";

interface ProductionSetDocument {
  id: string;
  production_set_id: string;
  document_id: string;
  bates_begin: string | null;
  bates_end: string | null;
  filename: string | null;
  added_at: string;
}

interface Props {
  productionSetId: string;
  onBack: () => void;
  onRefresh: () => void;
}

export function ProductionSetDetail({ productionSetId, onBack, onRefresh }: Props) {
  const matterId = useAppStore((s) => s.matterId);
  const queryClient = useQueryClient();
  const [offset, setOffset] = useState(0);
  const limit = 50;

  const { data, isLoading } = useQuery({
    queryKey: ["production-set-docs", productionSetId, offset],
    queryFn: () =>
      apiClient<PaginatedResponse<ProductionSetDocument>>({
        url: `/api/v1/exports/production-sets/${productionSetId}/documents`,
        method: "GET",
        params: { offset, limit },
      }),
    enabled: !!matterId,
  });

  const removeMutation = useMutation({
    mutationFn: (docId: string) =>
      apiClient<void>({
        url: `/api/v1/exports/production-sets/${productionSetId}/documents/${docId}`,
        method: "DELETE",
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["production-set-docs", productionSetId],
      });
      onRefresh();
    },
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="icon" onClick={onBack}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <h2 className="text-lg font-semibold">
          Production Set Documents
        </h2>
        <span className="text-sm text-muted-foreground">
          {data ? `${data.total} documents` : ""}
        </span>
      </div>

      {isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-12 w-full" />
          ))}
        </div>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Filename</TableHead>
              <TableHead>Bates Begin</TableHead>
              <TableHead>Bates End</TableHead>
              <TableHead>Added</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {(data?.items ?? []).length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} className="text-center text-muted-foreground py-8">
                  No documents in this production set.
                </TableCell>
              </TableRow>
            ) : (
              data?.items.map((doc) => (
                <TableRow key={doc.id}>
                  <TableCell className="font-medium">
                    {doc.filename ?? doc.document_id}
                  </TableCell>
                  <TableCell className="font-mono text-xs">
                    {doc.bates_begin ?? "—"}
                  </TableCell>
                  <TableCell className="font-mono text-xs">
                    {doc.bates_end ?? "—"}
                  </TableCell>
                  <TableCell className="text-muted-foreground text-xs">
                    {new Date(doc.added_at).toLocaleDateString()}
                  </TableCell>
                  <TableCell>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => removeMutation.mutate(doc.document_id)}
                      disabled={removeMutation.isPending}
                    >
                      <Trash2 className="h-4 w-4 text-destructive" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      )}

      {data && data.total > limit && (
        <Pagination
          total={data.total}
          offset={offset}
          limit={limit}
          onOffsetChange={setOffset}
        />
      )}
    </div>
  );
}
