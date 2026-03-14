import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { useAppStore } from "@/stores/app-store";
import { apiClient } from "@/api/client";
import { queryClient } from "@/main";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Tooltip,
  TooltipTrigger,
  TooltipContent,
} from "@/components/ui/tooltip";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import type { Matter } from "@/types";

export function MatterSelector() {
  const matterId = useAppStore((s) => s.matterId);
  const setMatter = useAppStore((s) => s.setMatter);
  const navigate = useNavigate();
  const [pendingMatterId, setPendingMatterId] = useState<string | null>(null);

  const { data: matters } = useQuery({
    queryKey: ["matters"],
    queryFn: () =>
      apiClient<Matter[]>({ url: "/api/v1/auth/me/matters", method: "GET" }),
  });

  // Auto-select the first matter when none is selected
  useEffect(() => {
    if (!matterId && matters && matters.length > 0) {
      setMatter(matters[0]!.id);
    }
  }, [matterId, matters, setMatter]);

  const pendingMatterName = pendingMatterId
    ? matters?.find((m) => m.id === pendingMatterId)?.name
    : null;

  function handleValueChange(value: string) {
    if (value === matterId) return;
    setPendingMatterId(value);
  }

  function handleConfirm() {
    if (!pendingMatterId) return;
    setMatter(pendingMatterId);
    queryClient.invalidateQueries();
    setPendingMatterId(null);
    navigate({ to: "/" });
  }

  return (
    <>
      <Select value={matterId ?? undefined} onValueChange={handleValueChange}>
        <Tooltip>
          <TooltipTrigger asChild>
            <SelectTrigger className="min-w-0 max-w-[280px]">
              <span className="flex items-center">
                <span className="mr-2 text-xs text-muted-foreground">Case:</span>
                <SelectValue placeholder="Select matter..." />
              </span>
            </SelectTrigger>
          </TooltipTrigger>
          <TooltipContent side="bottom">
            {matters?.find((m) => m.id === matterId)?.name ?? "Select matter..."}
          </TooltipContent>
        </Tooltip>
        <SelectContent>
          {matters?.map((m) => (
            <SelectItem key={m.id} value={m.id}>
              {m.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Dialog
        open={!!pendingMatterId}
        onOpenChange={(open) => {
          if (!open) setPendingMatterId(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Switch Active Case?</DialogTitle>
            <DialogDescription>
              This will switch the active case to{" "}
              <span className="font-medium text-foreground">
                {pendingMatterName}
              </span>
              . All views will reload with data from the new case.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setPendingMatterId(null)}
            >
              Cancel
            </Button>
            <Button onClick={handleConfirm}>Switch</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
