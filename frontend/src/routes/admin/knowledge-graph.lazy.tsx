import { useState } from "react";
import { createLazyFileRoute } from "@tanstack/react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useNotifications } from "@/hooks/use-notifications";

export const Route = createLazyFileRoute("/admin/knowledge-graph")({
  component: KnowledgeGraphPage,
});

interface DocumentEntityStatus {
  doc_id: string;
  filename: string;
  entity_count: number;
  neo4j_indexed: boolean;
  created_at: string;
}

interface KGStatusResponse {
  total_nodes: number;
  total_edges: number;
  node_counts: Record<string, number>;
  edge_counts: Record<string, number>;
  documents: DocumentEntityStatus[];
  total_documents: number;
  indexed_documents: number;
}

interface KGTaskResponse {
  task_id: string;
  document_count?: number;
  mode?: string;
}

function KnowledgeGraphPage() {
  const [selectedDocs, setSelectedDocs] = useState<Set<string>>(new Set());
  const notify = useNotifications();
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["kg-status"],
    queryFn: () =>
      apiClient<KGStatusResponse>({
        url: "/api/v1/admin/knowledge-graph/status",
        method: "GET",
      }),
  });

  const reprocessMutation = useMutation({
    mutationFn: (payload: { document_ids?: string[]; all_unprocessed?: boolean }) =>
      apiClient<KGTaskResponse>({
        url: "/api/v1/admin/knowledge-graph/reprocess",
        method: "POST",
        data: payload,
      }),
    onSuccess: (result) => {
      notify.success(`Reprocessing started: task ${result.task_id} dispatched for ${result.document_count} documents.`);
      setSelectedDocs(new Set());
      queryClient.invalidateQueries({ queryKey: ["kg-status"] });
    },
    onError: (err) => {
      notify.error(err instanceof Error ? err.message : "Failed to start reprocessing");
    },
  });

  const resolveMutation = useMutation({
    mutationFn: (mode: string) =>
      apiClient<KGTaskResponse>({
        url: "/api/v1/admin/knowledge-graph/resolve",
        method: "POST",
        data: { mode },
      }),
    onSuccess: (result) => {
      notify.success(`Resolution started: task ${result.task_id} dispatched (${result.mode} mode).`);
    },
    onError: (err) => {
      notify.error(err instanceof Error ? err.message : "Failed to start resolution");
    },
  });

  function toggleDoc(docId: string) {
    setSelectedDocs((prev) => {
      const next = new Set(prev);
      if (next.has(docId)) next.delete(docId);
      else next.add(docId);
      return next;
    });
  }

  function toggleAll() {
    if (!data) return;
    if (selectedDocs.size === data.documents.length) {
      setSelectedDocs(new Set());
    } else {
      setSelectedDocs(new Set(data.documents.map((d) => d.doc_id)));
    }
  }

  return (
    <div className="space-y-6 animate-page-in">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Graph Admin</h1>
        <p className="text-sm text-muted-foreground">
          Monitor graph health, reprocess documents, and run entity resolution.
        </p>
      </div>

      {/* Section 1: Graph Health */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Graph Health</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <p className="text-sm text-muted-foreground">Loading...</p>
          ) : data ? (
            <div className="space-y-4">
              <div className="flex gap-6">
                <div>
                  <p className="text-2xl font-bold tabular-nums">{data.total_nodes.toLocaleString()}</p>
                  <p className="text-xs text-muted-foreground">Total Nodes</p>
                </div>
                <div>
                  <p className="text-2xl font-bold tabular-nums">{data.total_edges.toLocaleString()}</p>
                  <p className="text-xs text-muted-foreground">Total Edges</p>
                </div>
                <div>
                  <p className="text-2xl font-bold tabular-nums">{data.indexed_documents}/{data.total_documents}</p>
                  <p className="text-xs text-muted-foreground">Docs Indexed</p>
                </div>
              </div>
              {Object.keys(data.node_counts).length > 0 && (
                <div>
                  <p className="text-xs font-medium text-muted-foreground mb-2">Node Types</p>
                  <div className="flex flex-wrap gap-1.5">
                    {Object.entries(data.node_counts).map(([type, count]) => (
                      <Badge key={type} variant="secondary">
                        {type}: {count}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">Unable to load graph stats.</p>
          )}
        </CardContent>
      </Card>

      {/* Section 2: Document Table */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-base">Document Processing Status</CardTitle>
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="outline"
              disabled={selectedDocs.size === 0 || reprocessMutation.isPending}
              onClick={() => reprocessMutation.mutate({ document_ids: [...selectedDocs] })}
            >
              Re-process Selected ({selectedDocs.size})
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={reprocessMutation.isPending}
              onClick={() => reprocessMutation.mutate({ all_unprocessed: true })}
            >
              Re-process All Unprocessed
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={resolveMutation.isPending}
              onClick={() => resolveMutation.mutate("simple")}
            >
              Resolve Entities
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={resolveMutation.isPending}
              onClick={() => resolveMutation.mutate("agent")}
            >
              Resolve (Agent)
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <p className="text-sm text-muted-foreground">Loading documents...</p>
          ) : data && data.documents.length > 0 ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-10">
                    <Checkbox
                      checked={data.documents.length > 0 && selectedDocs.size === data.documents.length}
                      onCheckedChange={toggleAll}
                    />
                  </TableHead>
                  <TableHead>Filename</TableHead>
                  <TableHead className="text-right">Entities</TableHead>
                  <TableHead>Neo4j</TableHead>
                  <TableHead>Created</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.documents.map((doc) => (
                  <TableRow key={doc.doc_id}>
                    <TableCell>
                      <Checkbox
                        checked={selectedDocs.has(doc.doc_id)}
                        onCheckedChange={() => toggleDoc(doc.doc_id)}
                      />
                    </TableCell>
                    <TableCell className="font-mono text-xs max-w-[300px] truncate">{doc.filename}</TableCell>
                    <TableCell className="text-right tabular-nums">{doc.entity_count}</TableCell>
                    <TableCell>
                      <Badge variant={doc.neo4j_indexed ? "default" : "destructive"}>
                        {doc.neo4j_indexed ? "Indexed" : "Missing"}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-muted-foreground whitespace-nowrap">
                      {new Date(doc.created_at).toLocaleDateString()}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <p className="text-sm text-muted-foreground">No documents found.</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
