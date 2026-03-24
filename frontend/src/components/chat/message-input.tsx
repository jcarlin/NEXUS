import { useState, useRef, useCallback } from "react";
import { Send, Square } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { apiClient } from "@/api/client";

interface MessageInputProps {
  onSend: (text: string) => void;
  onStop?: () => void;
  isStreaming?: boolean;
  disabled?: boolean;
  variant?: "default" | "standalone" | "hero";
}

type ActiveModelResponse = {
  tier: string;
  model: string;
  provider_type: string | null;
};

export function MessageInput({ onSend, onStop, isStreaming, disabled, variant = "default" }: MessageInputProps) {
  const [text, setText] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const { data: activeModel } = useQuery({
    queryKey: ["active-model"],
    queryFn: () =>
      apiClient<ActiveModelResponse>({
        url: "/api/v1/llm-config/active-model",
        method: "GET",
      }),
    staleTime: 5 * 60 * 1000,
    retry: false,
  });

  const handleSubmit = useCallback(() => {
    const trimmed = text.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setText("");
    // Reset textarea height
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  }, [text, disabled, onSend]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleInput = () => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 200) + "px";
  };

  return (
    <div
      className={cn(
        variant === "hero" ? "w-full" : "bg-background px-4 pt-4 pb-3",
        variant === "default" && "border-t",
      )}
    >
      {variant !== "hero" && activeModel?.model && (
        <Badge variant="outline" className="mb-2 text-[11px] font-normal text-muted-foreground">
          {activeModel.model}
        </Badge>
      )}

      {variant === "hero" ? (
        <div className="overflow-hidden rounded-xl border border-border/60 bg-card shadow-lg shadow-primary/5 transition-colors focus-within:border-primary/40 focus-within:ring-1 focus-within:ring-primary/20">
          <textarea
            ref={textareaRef}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={handleKeyDown}
            onInput={handleInput}
            placeholder="Ask a question about the investigation..."
            rows={4}
            disabled={disabled}
            className="w-full resize-none border-0 bg-transparent px-4 pt-4 pb-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none disabled:opacity-50"
          />
          <div className="flex items-center justify-between px-4 pb-3">
            <div className="flex items-center gap-2">
              {activeModel?.model && (
                <Badge variant="outline" className="text-[11px] font-normal text-muted-foreground">
                  {activeModel.model}
                </Badge>
              )}
            </div>
            {isStreaming ? (
              <Button
                size="icon-sm"
                variant="destructive"
                aria-label="Stop generating"
                onClick={onStop}
              >
                <Square className="h-3.5 w-3.5" />
              </Button>
            ) : (
              <Button
                size="icon-sm"
                aria-label="Send"
                onClick={handleSubmit}
                disabled={disabled || !text.trim()}
              >
                <Send className="h-4 w-4" />
              </Button>
            )}
          </div>
        </div>
      ) : (
        <>
          <div className="flex items-end gap-2">
            <textarea
              ref={textareaRef}
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={handleKeyDown}
              onInput={handleInput}
              placeholder="Ask a question about the investigation..."
              rows={1}
              disabled={disabled}
              className="flex-1 resize-none rounded-md border border-border/60 bg-transparent px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus:border-primary/40 focus:ring-1 focus:ring-primary/20 transition-colors disabled:opacity-50"
            />
            {isStreaming ? (
              <Button
                size="icon"
                variant="destructive"
                aria-label="Stop generating"
                onClick={onStop}
              >
                <Square className="h-3.5 w-3.5" />
              </Button>
            ) : (
              <Button
                size="icon"
                aria-label="Send"
                onClick={handleSubmit}
                disabled={disabled || !text.trim()}
              >
                <Send className="h-4 w-4" />
              </Button>
            )}
          </div>
          <p className="px-1 pt-1 text-[11px] text-muted-foreground/50">
            Enter to send · Shift+Enter for new line
          </p>
        </>
      )}
    </div>
  );
}
