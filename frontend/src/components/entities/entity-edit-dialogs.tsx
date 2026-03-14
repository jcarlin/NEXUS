import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { apiClient } from "@/api/client";
import { useAppStore } from "@/stores/app-store";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

const ENTITY_TYPES = ["person", "organization", "location", "date", "monetary_amount"] as const;

interface RenameDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  entityName: string;
}

export function RenameDialog({ open, onOpenChange, entityName }: RenameDialogProps) {
  const [newName, setNewName] = useState(entityName);
  const matterId = useAppStore((s) => s.matterId);
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: () =>
      apiClient({
        url: `/api/v1/matters/${matterId}/entities/${encodeURIComponent(entityName)}/rename`,
        method: "PATCH",
        data: { new_name: newName },
      }),
    onSuccess: () => {
      toast.success(`Renamed "${entityName}" to "${newName}"`);
      void queryClient.invalidateQueries({ queryKey: ["entities"] });
      void queryClient.invalidateQueries({ queryKey: ["entity-connections"] });
      onOpenChange(false);
    },
    onError: () => toast.error("Failed to rename entity"),
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Rename Entity</DialogTitle>
          <DialogDescription>Rename &ldquo;{entityName}&rdquo; across the knowledge graph.</DialogDescription>
        </DialogHeader>
        <div className="space-y-2">
          <Label htmlFor="new-name">New name</Label>
          <Input id="new-name" value={newName} onChange={(e) => setNewName(e.target.value)} />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={() => mutation.mutate()} disabled={mutation.isPending || !newName.trim() || newName === entityName}>
            {mutation.isPending ? "Renaming..." : "Rename"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

interface ChangeTypeDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  entityName: string;
  currentType: string;
}

export function ChangeTypeDialog({ open, onOpenChange, entityName, currentType }: ChangeTypeDialogProps) {
  const [newType, setNewType] = useState(currentType);
  const matterId = useAppStore((s) => s.matterId);
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: () =>
      apiClient({
        url: `/api/v1/matters/${matterId}/entities/${encodeURIComponent(entityName)}/type`,
        method: "PATCH",
        data: { new_type: newType },
      }),
    onSuccess: () => {
      toast.success(`Changed type of "${entityName}" to "${newType}"`);
      void queryClient.invalidateQueries({ queryKey: ["entities"] });
      void queryClient.invalidateQueries({ queryKey: ["entity-connections"] });
      onOpenChange(false);
    },
    onError: () => toast.error("Failed to change entity type"),
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Change Entity Type</DialogTitle>
          <DialogDescription>Change the type of &ldquo;{entityName}&rdquo;.</DialogDescription>
        </DialogHeader>
        <div className="space-y-2">
          <Label>New type</Label>
          <Select value={newType} onValueChange={setNewType}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {ENTITY_TYPES.map((t) => (
                <SelectItem key={t} value={t}>{t}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={() => mutation.mutate()} disabled={mutation.isPending || newType === currentType}>
            {mutation.isPending ? "Updating..." : "Update"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

interface MergeDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  entityName: string;
}

export function MergeDialog({ open, onOpenChange, entityName }: MergeDialogProps) {
  const [targetName, setTargetName] = useState("");
  const matterId = useAppStore((s) => s.matterId);
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: () =>
      apiClient({
        url: `/api/v1/matters/${matterId}/entities/merge`,
        method: "POST",
        data: { source_name: entityName, target_name: targetName },
      }),
    onSuccess: () => {
      toast.success(`Merged "${entityName}" into "${targetName}"`);
      void queryClient.invalidateQueries({ queryKey: ["entities"] });
      void queryClient.invalidateQueries({ queryKey: ["entity-connections"] });
      onOpenChange(false);
    },
    onError: () => toast.error("Failed to merge entities"),
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Merge Entity</DialogTitle>
          <DialogDescription>Merge &ldquo;{entityName}&rdquo; into another entity. The source entity will be removed and its relationships transferred.</DialogDescription>
        </DialogHeader>
        <div className="space-y-2">
          <Label htmlFor="target-name">Merge into (target entity name)</Label>
          <Input id="target-name" value={targetName} onChange={(e) => setTargetName(e.target.value)} placeholder="Enter target entity name" />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={() => mutation.mutate()} disabled={mutation.isPending || !targetName.trim() || targetName === entityName}>
            {mutation.isPending ? "Merging..." : "Merge"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

interface DeleteConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  entityName: string;
}

export function DeleteConfirmDialog({ open, onOpenChange, entityName }: DeleteConfirmDialogProps) {
  const matterId = useAppStore((s) => s.matterId);
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: () =>
      apiClient({
        url: `/api/v1/matters/${matterId}/entities/${encodeURIComponent(entityName)}`,
        method: "DELETE",
      }),
    onSuccess: () => {
      toast.success(`Deleted "${entityName}"`);
      void queryClient.invalidateQueries({ queryKey: ["entities"] });
      void queryClient.invalidateQueries({ queryKey: ["entity-connections"] });
      onOpenChange(false);
    },
    onError: () => toast.error("Failed to delete entity"),
  });

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete Entity</AlertDialogTitle>
          <AlertDialogDescription>
            This will permanently delete &ldquo;{entityName}&rdquo; and all its relationships from the knowledge graph. This action cannot be undone.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending}
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
          >
            {mutation.isPending ? "Deleting..." : "Delete"}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
