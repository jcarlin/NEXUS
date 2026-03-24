import { createLazyFileRoute } from "@tanstack/react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, useEffect } from "react";
import { useViewState } from "@/hooks/use-view-state";
import {
  ChevronRight,
  ChevronDown,
  Folder,
  FolderOpen,
  Plus,
  Trash2,
  Shield,
  Upload,
  X,
} from "lucide-react";
import { apiClient } from "@/api/client";
import { useAppStore } from "@/stores/app-store";
import { useAuthStore } from "@/stores/auth-store";
import { buildDragPayload, toggleSelection, isAllSelected } from "@/lib/dataset-dnd";
import { canManageDatasetAccess } from "@/lib/dataset-access";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import { DatasetAccessDialog } from "@/components/datasets/dataset-access-dialog";
import { IngestDialog } from "@/components/datasets/ingest-dialog";
import { IngestProgress } from "@/components/datasets/ingest-progress";
import type {
  DatasetTreeResponse,
  DatasetTreeNode,
  DatasetResponse,
  DocumentResponse,
  PaginatedResponse,
} from "@/types";

export const Route = createLazyFileRoute("/datasets/")({
  component: DatasetsPage,
});

function TreeItem({
  node,
  depth,
  selectedId,
  onSelect,
  onDrop,
}: {
  node: DatasetTreeNode;
  depth: number;
  selectedId: string | null;
  onSelect: (id: string) => void;
  onDrop: (targetDatasetId: string, documentIds: string[]) => void;
}) {
  const [expanded, setExpanded] = useState(depth === 0);
  const [isDropTarget, setIsDropTarget] = useState(false);
  const hasChildren = node.children.length > 0;
  const isSelected = selectedId === node.id;

  return (
    <div>
      <div
        className={`flex cursor-pointer items-center gap-1 rounded-md px-2 py-1.5 text-sm hover:bg-accent ${isSelected ? "bg-accent text-accent-foreground" : ""} ${isDropTarget ? "ring-2 ring-primary bg-primary/10" : ""}`}
        style={{ paddingLeft: `${depth * 16 + 8}px` }}
        onClick={() => onSelect(node.id)}
        onDragOver={(e) => {
          e.preventDefault();
          e.dataTransfer.dropEffect = "move";
          setIsDropTarget(true);
        }}
        onDragEnter={(e) => {
          e.preventDefault();
          setIsDropTarget(true);
        }}
        onDragLeave={(e) => {
          if (!e.currentTarget.contains(e.relatedTarget as Node)) {
            setIsDropTarget(false);
          }
        }}
        onDrop={(e) => {
          e.preventDefault();
          setIsDropTarget(false);
          const raw = e.dataTransfer.getData("application/json");
          if (!raw) return;
          try {
            const documentIds: string[] = JSON.parse(raw);
            if (documentIds.length > 0) {
              onDrop(node.id, documentIds);
            }
          } catch {
            /* ignore malformed data */
          }
        }}
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
            onDrop={onDrop}
          />
        ))}
    </div>
  );
}

function DatasetsPage() {
  const matterId = useAppStore((s) => s.matterId);
  const userRole = useAuthStore((s) => s.user?.role);
  const queryClient = useQueryClient();
  const [vs, setVS] = useViewState("/datasets", {
    selectedId: null,
    docOffset: 0,
  });
  const selectedId = vs.selectedId;
  const setSelectedId = (id: string | null) => setVS({ selectedId: id, docOffset: 0 });
  const docOffset = vs.docOffset;
  const setDocOffset = (offset: number) => setVS({ docOffset: offset });
  const [createOpen, setCreateOpen] = useState(false);
  const [accessOpen, setAccessOpen] = useState(false);
  const [ingestOpen, setIngestOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [ingestAfterCreate, setIngestAfterCreate] = useState(false);
  const [selectedDocIds, setSelectedDocIds] = useState<Set<string>>(new Set());
  const docLimit = 50;

  // Clear selection when dataset or page changes
  useEffect(() => {
    setSelectedDocIds(new Set());
  }, [selectedId, docOffset]);

  const showPermissions = canManageDatasetAccess(userRole);

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
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ["datasets"] });
      setCreateOpen(false);
      setNewName("");
      setNewDescription("");
      if (ingestAfterCreate) {
        setSelectedId(result.id);
        setIngestOpen(true);
        setIngestAfterCreate(false);
      }
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

  const moveMutation = useMutation({
    mutationFn: (data: {
      sourceDatasetId: string;
      documentIds: string[];
      targetDatasetId: string;
    }) =>
      apiClient<{ moved: number }>({
        url: `/api/v1/datasets/${data.sourceDatasetId}/documents/move`,
        method: "POST",
        data: {
          document_ids: data.documentIds,
          target_dataset_id: data.targetDatasetId,
        },
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["datasets"] });
      setSelectedDocIds(new Set());
    },
  });

  function handleDrop(targetDatasetId: string, documentIds: string[]) {
    if (selectedId && targetDatasetId !== selectedId) {
      moveMutation.mutate({
        sourceDatasetId: selectedId,
        documentIds,
        targetDatasetId,
      });
    }
  }

  const pageDocIds = documents?.items.map((d) => d.id) ?? [];
  const allSelected = isAllSelected(selectedDocIds, pageDocIds);

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
                  onDrop={handleDrop}
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
                  size="sm"
                  className="h-7 gap-1 px-2"
                  onClick={() => setIngestOpen(true)}
                  title="Ingest documents"
                >
                  <Upload className="h-4 w-4" />
                  <span className="text-xs">Ingest</span>
                </Button>
                {showPermissions && (
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7"
                    onClick={() => setAccessOpen(true)}
                    title="Manage permissions"
                  >
                    <Shield className="h-4 w-4" />
                  </Button>
                )}
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

            <IngestProgress datasetId={selectedId} />

            {/* Selection indicator */}
            {selectedDocIds.size > 0 && (
              <div className="flex items-center gap-2 border-b bg-muted/50 px-4 py-1.5">
                <span className="text-xs font-medium">
                  {selectedDocIds.size} selected
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-6 px-2 text-xs"
                  onClick={() => setSelectedDocIds(new Set())}
                >
                  <X className="mr-1 h-3 w-3" />
                  Clear
                </Button>
                <span className="text-xs text-muted-foreground">
                  Drag to a folder to move
                </span>
              </div>
            )}

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
                  {/* Select all header */}
                  <div className="flex items-center gap-3 px-4 py-1.5 text-xs text-muted-foreground">
                    <Checkbox
                      checked={allSelected}
                      onCheckedChange={() => {
                        if (allSelected) {
                          setSelectedDocIds(new Set());
                        } else {
                          setSelectedDocIds(new Set(pageDocIds));
                        }
                      }}
                    />
                    <span>Select all</span>
                  </div>
                  {documents?.items.map((doc) => {
                    const isDocSelected = selectedDocIds.has(doc.id);
                    return (
                      <div
                        key={doc.id}
                        className={`flex cursor-grab items-center gap-3 px-4 py-2 ${isDocSelected ? "bg-accent/50" : ""}`}
                        draggable
                        onDragStart={(e) => {
                          const ids = buildDragPayload(doc.id, selectedDocIds);
                          e.dataTransfer.setData(
                            "application/json",
                            JSON.stringify(ids),
                          );
                          e.dataTransfer.effectAllowed = "move";
                        }}
                      >
                        <Checkbox
                          checked={isDocSelected}
                          onCheckedChange={() =>
                            setSelectedDocIds(
                              toggleSelection(selectedDocIds, doc.id),
                            )
                          }
                        />
                        <div className="min-w-0 flex-1">
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
                    );
                  })}
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
            <div className="flex items-center gap-2">
              <Checkbox
                id="ingest-after-create"
                checked={ingestAfterCreate}
                onCheckedChange={(checked) =>
                  setIngestAfterCreate(!!checked)
                }
              />
              <Label htmlFor="ingest-after-create" className="text-sm font-normal">
                Ingest documents into this dataset after creation
              </Label>
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

      {/* Access control dialog */}
      {showPermissions && selectedId && (
        <DatasetAccessDialog
          open={accessOpen}
          onOpenChange={setAccessOpen}
          datasetId={selectedId}
        />
      )}

      {/* Ingest dialog */}
      {selectedId && (
        <IngestDialog
          open={ingestOpen}
          onOpenChange={setIngestOpen}
          datasetId={selectedId}
          onStarted={() =>
            queryClient.invalidateQueries({
              queryKey: ["datasets", selectedId, "ingest"],
            })
          }
        />
      )}
    </div>
  );
}
