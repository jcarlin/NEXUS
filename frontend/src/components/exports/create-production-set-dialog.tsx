import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { apiClient } from "@/api/client";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

interface Props {
  onCreated: () => void;
}

export function CreateProductionSetDialog({ onCreated }: Props) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [batesPrefix, setBatesPrefix] = useState("NEXUS");

  const mutation = useMutation({
    mutationFn: () =>
      apiClient<unknown>({
        url: "/api/v1/exports/production-sets",
        method: "POST",
        data: {
          name,
          description: description || null,
          bates_prefix: batesPrefix,
        },
      }),
    onSuccess: () => {
      setOpen(false);
      setName("");
      setDescription("");
      setBatesPrefix("NEXUS");
      onCreated();
    },
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          <Plus className="mr-1.5 h-3.5 w-3.5" />
          New Production Set
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Create Production Set</DialogTitle>
        </DialogHeader>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            mutation.mutate();
          }}
        >
          <div className="space-y-2">
            <Label htmlFor="ps-name">Name</Label>
            <Input
              id="ps-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g., First Production"
              required
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="ps-description">Description</Label>
            <Input
              id="ps-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Optional description"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="ps-bates">Bates Prefix</Label>
            <Input
              id="ps-bates"
              value={batesPrefix}
              onChange={(e) => setBatesPrefix(e.target.value)}
              placeholder="NEXUS"
            />
          </div>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={!name.trim() || mutation.isPending}>
              {mutation.isPending ? "Creating..." : "Create"}
            </Button>
          </div>
          {mutation.isError && (
            <p className="text-sm text-destructive">
              {mutation.error.message}
            </p>
          )}
        </form>
      </DialogContent>
    </Dialog>
  );
}
