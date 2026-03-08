import { useState } from "react";
import { FileText, Loader2 } from "lucide-react";
import { useMutation } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { apiClient } from "@/api/client";
import { useAppStore } from "@/stores/app-store";
import { useNotifications } from "@/hooks/use-notifications";
import { MemoViewerDialog } from "./memo-viewer-dialog";
import type { MemoResponse } from "@/types";

interface GenerateMemoButtonProps {
  threadId: string;
}

export function GenerateMemoButton({ threadId }: GenerateMemoButtonProps) {
  const [viewerOpen, setViewerOpen] = useState(false);
  const [memo, setMemo] = useState<MemoResponse | null>(null);
  const notify = useNotifications();

  const mutation = useMutation({
    mutationFn: () => {
      const matterId = useAppStore.getState().matterId;
      return apiClient<MemoResponse>({
        url: "/api/v1/memos",
        method: "POST",
        data: { thread_id: threadId, matter_id: matterId },
      });
    },
    onSuccess: (data) => {
      setMemo(data);
      setViewerOpen(true);
      notify.success(`Memo generated: ${data.title}`);
    },
    onError: (err: Error) => {
      notify.error(err.message || "Failed to generate memo");
    },
  });

  return (
    <>
      <Button
        variant="ghost"
        size="sm"
        className="h-7 gap-1.5 text-xs text-muted-foreground"
        onClick={() => mutation.mutate()}
        disabled={mutation.isPending}
      >
        {mutation.isPending ? (
          <Loader2 className="h-3 w-3 animate-spin" />
        ) : (
          <FileText className="h-3 w-3" />
        )}
        Memo
      </Button>
      <MemoViewerDialog memo={memo} open={viewerOpen} onOpenChange={setViewerOpen} />
    </>
  );
}
