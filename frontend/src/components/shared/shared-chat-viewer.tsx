import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchEventSource } from "@microsoft/fetch-event-source";
import {
  Loader2,
  MessageSquare,
  Send,
  FileText,
  AlertCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { MarkdownMessage } from "@/components/chat/markdown-message";
import type { ChatMessage } from "@/types";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "";

interface SharedChatData {
  thread_id: string;
  messages: ChatMessage[];
  allow_follow_ups: boolean;
  created_at: string;
  expires_at: string | null;
  first_query: string;
  first_response_preview: string;
}

interface SharedChatViewerProps {
  token: string;
}

export function SharedChatViewer({ token }: SharedChatViewerProps) {
  const [inputValue, setInputValue] = useState("");
  const [streamingText, setStreamingText] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [stage, setStage] = useState<string | null>(null);
  const [streamError, setStreamError] = useState<string | null>(null);
  const [pendingMessage, setPendingMessage] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const {
    data,
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: ["shared-chat", token],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/api/v1/shared/${token}`);
      if (!res.ok) {
        if (res.status === 404) throw new Error("not_found");
        throw new Error(`Failed to load: ${res.status}`);
      }
      return res.json() as Promise<SharedChatData>;
    },
    retry: false,
  });

  // Auto-scroll to bottom on new content
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [data?.messages, streamingText, pendingMessage]);

  const handleSend = useCallback(async () => {
    const query = inputValue.trim();
    if (!query || isStreaming) return;

    setInputValue("");
    setPendingMessage(query);
    setStreamingText("");
    setStage("connecting");
    setIsStreaming(true);
    setStreamError(null);

    const ctrl = new AbortController();
    abortRef.current = ctrl;

    try {
      await fetchEventSource(
        `${API_BASE}/api/v1/shared/${token}/query/stream`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ query }),
          signal: ctrl.signal,

          onopen: async (response) => {
            if (!response.ok) {
              if (response.status === 429) {
                throw new Error(
                  "Rate limit reached. Please wait a moment before asking another question.",
                );
              }
              if (response.status === 403) {
                throw new Error(
                  "Follow-up questions are disabled for this conversation.",
                );
              }
              throw new Error(`Stream failed: ${response.status}`);
            }
          },

          onmessage: (event) => {
            if (!event.data) return;
            try {
              const parsed = JSON.parse(event.data);
              switch (event.event) {
                case "status":
                  setStage(parsed.stage);
                  break;
                case "token":
                  setStreamingText((prev) => prev + parsed.text);
                  setStage("generating");
                  break;
                case "error":
                  setStreamError(parsed.message);
                  break;
                case "done":
                  setIsStreaming(false);
                  setStage(null);
                  setPendingMessage(null);
                  // Refetch to get the persisted messages
                  refetch();
                  break;
              }
            } catch {
              // skip malformed events
            }
          },

          onerror: (err) => {
            setStreamError(
              err instanceof Error ? err.message : "Connection lost",
            );
            setIsStreaming(false);
            setStage(null);
            throw err; // stop retrying
          },
        },
      );
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      setStreamError(
        err instanceof Error ? err.message : "Failed to send question",
      );
      setIsStreaming(false);
      setStage(null);
    }
  }, [inputValue, isStreaming, token, refetch]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend],
  );

  // Not found / expired
  if (error) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background p-4">
        <div className="max-w-md text-center">
          <AlertCircle className="mx-auto mb-4 h-12 w-12 text-muted-foreground" />
          <h1 className="mb-2 text-xl font-semibold">
            Conversation Not Found
          </h1>
          <p className="text-sm text-muted-foreground">
            This shared conversation may have expired or been removed.
          </p>
        </div>
      </div>
    );
  }

  // Loading
  if (isLoading || !data) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const messages = data.messages;

  return (
    <div className="flex min-h-screen flex-col bg-background">
      {/* Header */}
      <header className="border-b bg-background/95 px-4 py-3 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <div className="mx-auto flex max-w-3xl items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10">
            <MessageSquare className="h-4 w-4 text-primary" />
          </div>
          <div className="flex-1 min-w-0">
            <h1 className="text-sm font-semibold truncate">NEXUS</h1>
            <p className="text-xs text-muted-foreground">
              Shared Conversation
            </p>
          </div>
        </div>
      </header>

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-3xl px-4 py-6 space-y-6">
          {messages.map((msg, i) => (
            <MessageBubble key={i} message={msg} />
          ))}

          {/* Pending user message */}
          {pendingMessage && (
            <div className="flex justify-end">
              <div className="max-w-[80%] rounded-2xl rounded-br-md bg-primary px-4 py-2.5 text-sm text-primary-foreground">
                {pendingMessage}
              </div>
            </div>
          )}

          {/* Streaming response */}
          {(isStreaming || streamingText) && !streamError && (
            <div className="space-y-2">
              {stage && stage !== "generating" && (
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <Loader2 className="h-3 w-3 animate-spin" />
                  <span className="capitalize">
                    {stage.replace(/_/g, " ")}...
                  </span>
                </div>
              )}
              {streamingText && (
                <div className="rounded-2xl rounded-bl-md bg-muted px-4 py-3">
                  <MarkdownMessage content={streamingText} />
                </div>
              )}
            </div>
          )}

          {/* Stream error */}
          {streamError && (
            <div className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
              {streamError}
            </div>
          )}
        </div>
      </div>

      {/* Follow-up input */}
      {data.allow_follow_ups && (
        <div className="border-t bg-background px-4 py-3">
          <div className="mx-auto max-w-3xl">
            <div className="flex items-end gap-2">
              <textarea
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask a follow-up question..."
                rows={1}
                disabled={isStreaming}
                className="flex-1 resize-none rounded-lg border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring disabled:opacity-50"
              />
              <Button
                size="icon"
                onClick={handleSend}
                disabled={!inputValue.trim() || isStreaming}
                className="h-9 w-9 shrink-0"
              >
                {isStreaming ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Send className="h-4 w-4" />
                )}
              </Button>
            </div>
            <p className="mt-1.5 text-center text-[10px] text-muted-foreground">
              Powered by NEXUS - Legal Document Intelligence
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

function MessageBubble({ message }: { message: ChatMessage }) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] rounded-2xl rounded-br-md bg-primary px-4 py-2.5 text-sm text-primary-foreground">
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div className="rounded-2xl rounded-bl-md bg-muted px-4 py-3">
        <MarkdownMessage content={message.content} />
      </div>

      {/* Sources */}
      {message.source_documents.length > 0 && (
        <div className="flex flex-wrap gap-1.5 pl-1">
          {message.source_documents.slice(0, 5).map((doc, i) => (
            <span
              key={i}
              className="inline-flex items-center gap-1 rounded-md bg-muted/60 px-2 py-0.5 text-[11px] text-muted-foreground"
            >
              <FileText className="h-3 w-3" />
              {doc.filename}
              {doc.page != null && <span>p.{doc.page}</span>}
            </span>
          ))}
          {message.source_documents.length > 5 && (
            <span className="inline-flex items-center rounded-md bg-muted/60 px-2 py-0.5 text-[11px] text-muted-foreground">
              +{message.source_documents.length - 5} more
            </span>
          )}
        </div>
      )}
    </div>
  );
}
