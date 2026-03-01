import { createFileRoute } from "@tanstack/react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  ChevronRight,
  ChevronDown,
  Folder,
  FolderOpen,
  Plus,
  Trash2,
} from "lucide-react";
import { apiClient } from "@/api/client";
import { useAppStore } from "@/stores/app-store";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import type {
  DatasetTreeResponse,
  DatasetTreeNode,
  DatasetResponse,
  DocumentResponse,
  PaginatedResponse,
} from "@/types";

export const Route = createFileRoute("/datasets/")({
  component: DatasetsPage,
});

function TreeItem({
  node,
  depth,
  selectedId,
  onSelect,
}: {
  node: DatasetTreeNode;
  depth: number;
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const [expanded, setExpanded] = useState(depth === 0);
  const hasChildren = node.children.length > 0;
  const isSelected = selectedId === node.id;

  return (
    <div>
      <div
        className={`flex cursor-pointer items-center gap-1 rounded-md px-2 py-1.5 text-sm hover:bg-accent ${isSelected ? "bg-accent text-accent-foreground" : ""}`}
        style={{ paddingLeft: `${depth * 16 + 8}px` }}
        onClick={() => onSelect(node.id)}
      >
        {hasChildren ? (
          <button
            onClick={(e) => {
              e.stopPropagation();
              setExpanded(!expanded);
            }}
            className="shrink-0"
          >
            {expanded ? (
              <ChevronDown className="h-4 w-4" />
            ) : (
              <ChevronRight className="h-4 w-4" />
            )}
          </button>
        ) : (
          <span className="w-4" />
        )}
        {expanded && hasChildren ? (
          <FolderOpen className="h-4 w-4 shrink-0 text-muted-foreground" />
        ) : (
          <Folder className="h-4 w-4 shrink-0 text-muted-foreground" />
        )}
        <span className="truncate">{node.name}</span>
        <span className="ml-auto text-xs text-muted-foreground">
          {node.document_count}
        </span>
      </div>
      {expanded &&
        hasChildren &&
        node.children.map((child) => (
          <TreeItem
            key={child.id}
            node={child}
            depth={depth + 1}
            selectedId={selectedId}
            onSelect={onSelect}
          />
        ))}
    </div>
  );
}

function DatasetsPage() {
  const matterId = useAppStore((s) => s.matterId);
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [docOffset, setDocOffset] = useState(0);
  const docLimit = 50;

  const { data: tree, isLoading: treeLoading } = useQuery({
    queryKey: ["datasets", "tree", matterId],
    queryFn: () =>
      apiClient<DatasetTreeResponse>({
        url: "/api/v1/datasets/tree",
        method: "GET",
      }),
    enabled: !!matterId,
  });

  const { data: documents, isLoading: docsLoading } = useQuery({
    queryKey: ["datasets", selectedId, "documents", docOffset],
    queryFn: () =>
      apiClient<PaginatedResponse<DocumentResponse>>({
        url: `/api/v1/datasets/${selectedId}/documents`,
        method: "GET",
        params: { offset: docOffset, limit: docLimit },
      }),
    enabled: !!selectedId,
  });

  const createMutation = useMutation({
    mutationFn: (data: {
      name: string;
      description: string;
      parent_id: string | null;
    }) =>
      apiClient<DatasetResponse>({
        url: "/api/v1/datasets",
        method: "POST",
        data,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["datasets"] });
      setCreateOpen(false);
      setNewName("");
      setNewDescription("");
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) =>
      apiClient<void>({
        url: `/api/v1/datasets/${id}`,
        method: "DELETE",
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["datasets"] });
      setSelectedId(null);
    },
  });

  if (!matterId) {
    return (
      <div className="flex h-full items-center justify-center text-muted-foreground">
        Select a matter to view datasets
      </div>
    );
  }

  return (
    <div className="flex h-full gap-0 overflow-hidden">
      {/* Left panel: folder tree */}
      <div className="flex w-72 shrink-0 flex-col border-r">
        <div className="flex items-center justify-between border-b px-3 py-2">
          <h2 className="text-sm font-semibold">Datasets</h2>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            onClick={() => setCreateOpen(true)}
          >
            <Plus className="h-4 w-4" />
          </Button>
        </div>
        <ScrollArea className="flex-1">
          <div className="py-1">
            {treeLoading ? (
              <p className="px-3 py-4 text-sm text-muted-foreground">
                Loading...
              </p>
            ) : tree?.roots.length === 0 ? (
              <p className="px-3 py-4 text-sm text-muted-foreground">
                No datasets yet. Create one to get started.
              </p>
            ) : (
              tree?.roots.map((node) => (
                <TreeItem
                  key={node.id}
                  node={node}
                  depth={0}
                  selectedId={selectedId}
                  onSelect={(id) => {
                    setSelectedId(id);
                    setDocOffset(0);
                  }}
                />
              ))
            )}
          </div>
        </ScrollArea>
      </div>

      {/* Right panel: documents in selected dataset */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {selectedId ? (
          <>
            <div className="flex items-center justify-between border-b px-4 py-2">
              <span className="text-sm font-medium">
                {documents
                  ? `${documents.total} documents`
                  : "Loading..."}
              </span>
              <div className="flex items-center gap-2">
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7 text-destructive hover:text-destructive"
                  onClick={() => {
                    if (selectedId) deleteMutation.mutate(selectedId);
                  }}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            </div>
            <ScrollArea className="flex-1">
              {docsLoading ? (
                <p className="px-4 py-8 text-center text-sm text-muted-foreground">
                  Loading documents...
                </p>
              ) : documents?.items.length === 0 ? (
                <p className="px-4 py-8 text-center text-sm text-muted-foreground">
                  No documents in this dataset
                </p>
              ) : (
                <div className="divide-y">
                  {documents?.items.map((doc) => (
                    <div
                      key={doc.id}
                      className="flex items-center justify-between px-4 py-2"
                    >
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium">
                          {doc.filename}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {doc.page_count} pages &middot; {doc.chunk_count}{" "}
                          chunks
                        </p>
                      </div>
                      <span className="shrink-0 text-xs text-muted-foreground">
                        {doc.type ?? "unknown"}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </ScrollArea>
            {documents && documents.total > docLimit && (
              <div className="flex items-center justify-between border-t px-4 py-2">
                <span className="text-xs text-muted-foreground">
                  {docOffset + 1}--
                  {Math.min(docOffset + docLimit, documents.total)} of{" "}
                  {documents.total}
                </span>
                <div className="flex gap-1">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={docOffset === 0}
                    onClick={() =>
                      setDocOffset(Math.max(0, docOffset - docLimit))
                    }
                  >
                    Previous
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={docOffset + docLimit >= documents.total}
                    onClick={() => setDocOffset(docOffset + docLimit)}
                  >
                    Next
                  </Button>
                </div>
              </div>
            )}
          </>
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
            Select a dataset from the sidebar
          </div>
        )}
      </div>

      {/* Create dataset dialog */}
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create Dataset</DialogTitle>
            <DialogDescription>
              Create a new dataset to organize documents.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-2">
              <Label htmlFor="dataset-name">Name</Label>
              <Input
                id="dataset-name"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="e.g. Contracts 2024"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="dataset-desc">Description</Label>
              <Input
                id="dataset-desc"
                value={newDescription}
                onChange={(e) => setNewDescription(e.target.value)}
                placeholder="Optional description"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)}>
              Cancel
            </Button>
            <Button
              disabled={!newName.trim() || createMutation.isPending}
              onClick={() =>
                createMutation.mutate({
                  name: newName.trim(),
                  description: newDescription.trim(),
                  parent_id: selectedId,
                })
              }
            >
              {createMutation.isPending ? "Creating..." : "Create"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
