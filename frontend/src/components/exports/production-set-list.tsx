import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
import { Badge } from "@/components/ui/badge";
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
import { ProductionSetDetail } from "./production-set-detail";
import type { ProductionSet } from "@/routes/review/exports";

interface Props {
  data: ProductionSet[];
  loading: boolean;
  total: number;
  offset: number;
  limit: number;
  onOffsetChange: (offset: number) => void;
  onRefresh: () => void;
}

const statusColors: Record<string, string> = {
  draft: "bg-yellow-500/15 text-yellow-700",
  finalized: "bg-blue-500/15 text-blue-700",
  exported: "bg-green-500/15 text-green-700",
};

export function ProductionSetList({
  data,
  loading,
  total,
  offset,
  limit,
  onOffsetChange,
  onRefresh,
}: Props) {
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const batesMutation = useMutation({
    mutationFn: (psId: string) =>
      apiClient<ProductionSet>({
        url: `/api/v1/exports/production-sets/${psId}/assign-bates`,
        method: "POST",
      }),
    onSuccess: () => onRefresh(),
  });

  if (selectedId) {
    return (
      <ProductionSetDetail
        productionSetId={selectedId}
        onBack={() => setSelectedId(null)}
        onRefresh={onRefresh}
      />
    );
  }

  if (loading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Name</TableHead>
            <TableHead>Description</TableHead>
            <TableHead>Documents</TableHead>
            <TableHead>Bates Prefix</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Created</TableHead>
            <TableHead />
          </TableRow>
        </TableHeader>
        <TableBody>
          {data.length === 0 ? (
            <TableRow>
              <TableCell colSpan={7} className="text-center text-muted-foreground py-8">
                No production sets yet. Create one to get started.
              </TableCell>
            </TableRow>
          ) : (
            data.map((ps) => (
              <TableRow
                key={ps.id}
                className="cursor-pointer hover:bg-muted/50"
                onClick={() => setSelectedId(ps.id)}
              >
                <TableCell className="font-medium">{ps.name}</TableCell>
                <TableCell className="text-muted-foreground max-w-[200px] truncate">
                  {ps.description || "—"}
                </TableCell>
                <TableCell>{ps.document_count}</TableCell>
                <TableCell className="font-mono text-xs">{ps.bates_prefix}</TableCell>
                <TableCell>
                  <Badge variant="secondary" className={statusColors[ps.status] ?? ""}>
                    {ps.status}
                  </Badge>
                </TableCell>
                <TableCell className="text-muted-foreground text-xs">
                  {new Date(ps.created_at).toLocaleDateString()}
                </TableCell>
                <TableCell>
                  {ps.status === "draft" && (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={(e) => {
                        e.stopPropagation();
                        batesMutation.mutate(ps.id);
                      }}
                      disabled={batesMutation.isPending}
                    >
                      Assign Bates
                    </Button>
                  )}
                </TableCell>
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>

      {total > limit && (
        <Pagination
          total={total}
          offset={offset}
          limit={limit}
          onOffsetChange={onOffsetChange}
        />
      )}
    </div>
  );
}
