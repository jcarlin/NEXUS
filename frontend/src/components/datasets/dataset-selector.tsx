import { useQuery } from "@tanstack/react-query";
import { useAppStore } from "@/stores/app-store";
import { apiClient } from "@/api/client";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { DatasetTreeNode, DatasetTreeResponse } from "@/types";

function flattenTree(
  nodes: DatasetTreeNode[],
  depth = 0,
): { node: DatasetTreeNode; depth: number }[] {
  const result: { node: DatasetTreeNode; depth: number }[] = [];
  for (const node of nodes) {
    result.push({ node, depth });
    if (node.children.length > 0) {
      result.push(...flattenTree(node.children, depth + 1));
    }
  }
  return result;
}

export function DatasetSelector() {
  const matterId = useAppStore((s) => s.matterId);
  const datasetId = useAppStore((s) => s.datasetId);
  const setDataset = useAppStore((s) => s.setDataset);

  const { data } = useQuery({
    queryKey: ["datasets", "tree", matterId],
    queryFn: () =>
      apiClient<DatasetTreeResponse>({
        url: "/api/v1/datasets/tree",
        method: "GET",
      }),
    enabled: !!matterId,
  });

  const items = data ? flattenTree(data.roots) : [];

  if (!matterId) return null;

  return (
    <Select
      value={datasetId ?? "__all__"}
      onValueChange={(v) => setDataset(v === "__all__" ? null : v)}
    >
      <SelectTrigger className="w-[220px]">
        <span className="flex items-center gap-1.5">
          <span className="text-xs text-muted-foreground">Dataset:</span>
          <SelectValue placeholder="All Documents" />
        </span>
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="__all__">All Documents</SelectItem>
        {items.map(({ node, depth }) => (
          <SelectItem key={node.id} value={node.id}>
            <span style={{ paddingLeft: `${depth * 16}px` }}>
              {node.name}
              <span className="ml-1 text-xs text-muted-foreground">
                ({node.document_count})
              </span>
            </span>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
