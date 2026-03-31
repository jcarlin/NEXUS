import { useState, useCallback } from "react";
import { Share2, Check, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { apiClient } from "@/api/client";

interface ShareButtonProps {
  threadId: string;
}

interface ShareResponse {
  share_token: string;
  share_url: string;
  expires_at: string | null;
}

export function ShareButton({ threadId }: ShareButtonProps) {
  const [isLoading, setIsLoading] = useState(false);
  const [copied, setCopied] = useState(false);

  const handleShare = useCallback(async () => {
    setIsLoading(true);
    try {
      const result = await apiClient<ShareResponse>({
        url: `/api/v1/chats/${threadId}/share`,
        method: "POST",
        data: { allow_follow_ups: true },
      });

      await navigator.clipboard.writeText(result.share_url);
      setCopied(true);
      toast.success("Link copied! Share via SMS or WhatsApp.", {
        description: result.share_url,
        duration: 5000,
      });
      setTimeout(() => setCopied(false), 3000);
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Failed to create share link";
      if (message.includes("403")) {
        toast.error("Shareable links are not enabled.");
      } else {
        toast.error(message);
      }
    } finally {
      setIsLoading(false);
    }
  }, [threadId]);

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          className="h-7 gap-1.5 text-xs text-muted-foreground"
          onClick={handleShare}
          disabled={isLoading}
        >
          {isLoading ? (
            <Loader2 className="h-3 w-3 animate-spin" />
          ) : copied ? (
            <Check className="h-3 w-3 text-green-600" />
          ) : (
            <Share2 className="h-3 w-3" />
          )}
          {copied ? "Copied!" : "Share"}
        </Button>
      </TooltipTrigger>
      <TooltipContent>
        {copied ? "Link copied to clipboard" : "Create shareable link"}
      </TooltipContent>
    </Tooltip>
  );
}
