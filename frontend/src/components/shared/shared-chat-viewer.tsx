import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchEventSource } from "@microsoft/fetch-event-source";
import {
  Loader2,
  MessageSquare,
  Send,
  AlertCircle,
  ChevronDown,
  ChevronUp,
  BookOpen,
  Sparkles,
  ShieldCheck,
  ShieldAlert,
  ShieldQuestion,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { MarkdownMessage } from "@/components/chat/markdown-message";
import type { ChatMessage, CitedClaim } from "@/types";

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
            <MessageBubble
              key={i}
              message={msg}
              onFollowUpSelect={
                data.allow_follow_ups && msg.role === "assistant" && i === messages.length - 1
                  ? (q: string) => {
                      setInputValue(q);
                    }
                  : undefined
              }
            />
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
                  <MarkdownMessage content={streamingText} sources={[]} />
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

// ---------------------------------------------------------------------------
// Entity type colors (matches main chat)
// ---------------------------------------------------------------------------

const typeColors: Record<string, string> = {
  PERSON: "bg-blue-100 text-blue-800",
  ORGANIZATION: "bg-purple-100 text-purple-800",
  LOCATION: "bg-green-100 text-green-800",
  DATE: "bg-amber-100 text-amber-800",
  MONETARY: "bg-emerald-100 text-emerald-800",
  EMAIL: "bg-cyan-100 text-cyan-800",
  PHONE: "bg-orange-100 text-orange-800",
};

const verificationIcon = {
  verified: ShieldCheck,
  flagged: ShieldAlert,
  unverified: ShieldQuestion,
};

const verificationColor = {
  verified: "text-green-600",
  flagged: "text-red-600",
  unverified: "text-muted-foreground",
};

// ---------------------------------------------------------------------------
// MessageBubble — mirrors main chat's AssistantMessage
// ---------------------------------------------------------------------------

function MessageBubble({
  message,
  onFollowUpSelect,
}: {
  message: ChatMessage;
  onFollowUpSelect?: (q: string) => void;
}) {
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const [claimsOpen, setClaimsOpen] = useState(false);

  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] rounded-2xl rounded-br-md bg-primary px-4 py-2.5 text-sm text-primary-foreground">
          {message.content}
        </div>
      </div>
    );
  }

  const sources = message.source_documents;
  const entities = message.entities_mentioned;
  const citedClaims = message.cited_claims;
  const followUps = message.follow_up_questions;

  return (
    <div className="flex justify-start">
      <div className="space-y-2 max-w-full">
        {/* Label */}
        <div className="flex items-center gap-1.5 px-1">
          <Sparkles className="h-3.5 w-3.5 text-primary" />
          <span className="text-xs font-medium text-muted-foreground">NEXUS</span>
        </div>

        {/* Message content */}
        <div className="px-1">
          <div className="text-sm">
            <MarkdownMessage content={message.content} sources={sources} />
          </div>
        </div>

        {/* Entity chips */}
        {entities.length > 0 && (
          <div className="flex flex-wrap gap-1.5 px-1">
            {entities.map((entity) => {
              const colorClass =
                typeColors[entity.type.toUpperCase()] ??
                "bg-gray-100 text-gray-800";
              return (
                <Badge
                  key={entity.name}
                  variant="outline"
                  className={`border-0 text-xs ${colorClass}`}
                >
                  {entity.name}
                </Badge>
              );
            })}
          </div>
        )}

        {/* Source & claim toggle buttons */}
        <div className="flex items-center gap-2 px-1">
          {sources.length > 0 && (
            <Button
              variant="ghost"
              size="sm"
              className="h-7 gap-1.5 text-xs text-muted-foreground"
              onClick={() => setSourcesOpen(!sourcesOpen)}
            >
              <BookOpen className="h-3.5 w-3.5" />
              {sources.length} source{sources.length !== 1 ? "s" : ""}
              {sourcesOpen ? (
                <ChevronUp className="h-3 w-3" />
              ) : (
                <ChevronDown className="h-3 w-3" />
              )}
            </Button>
          )}

          {citedClaims.length > 0 && (
            <Button
              variant="ghost"
              size="sm"
              className="h-7 gap-1.5 text-xs text-muted-foreground"
              onClick={() => setClaimsOpen(!claimsOpen)}
            >
              {citedClaims.length} claim{citedClaims.length !== 1 ? "s" : ""}
              {claimsOpen ? (
                <ChevronUp className="h-3 w-3" />
              ) : (
                <ChevronDown className="h-3 w-3" />
              )}
            </Button>
          )}
        </div>

        {/* Expandable sources panel */}
        {sourcesOpen && sources.length > 0 && (
          <div className="rounded-md border">
            <div className="space-y-1 px-3 py-2">
              {sources.map((src, idx) => (
                <div
                  key={src.id}
                  className="flex items-start gap-2 rounded-md p-1.5 text-xs"
                >
                  <span className="mt-0.5 flex h-4 min-w-4 items-center justify-center rounded bg-primary/15 text-[10px] font-semibold text-primary">
                    {idx + 1}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium">{src.filename}</p>
                    {src.page != null && (
                      <span className="text-muted-foreground">
                        Page {src.page}
                      </span>
                    )}
                    {src.chunk_text && (
                      <p className="mt-0.5 line-clamp-2 text-muted-foreground">
                        {src.chunk_text}
                      </p>
                    )}
                  </div>
                  {src.relevance_score != null && (
                    <Badge variant="secondary" className="shrink-0 text-[10px]">
                      {(src.relevance_score * 100).toFixed(0)}%
                    </Badge>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Expandable claims panel */}
        {claimsOpen && citedClaims.length > 0 && (
          <div className="rounded-md border">
            <div className="space-y-2 px-3 py-2">
              {citedClaims.map((claim: CitedClaim, idx: number) => {
                const status = (claim.verification_status ?? "unverified") as keyof typeof verificationIcon;
                const Icon = verificationIcon[status] ?? ShieldQuestion;
                const color = verificationColor[status] ?? verificationColor.unverified;
                return (
                  <div
                    key={idx}
                    className="flex items-start gap-2 text-xs"
                  >
                    <Icon className={`mt-0.5 h-3.5 w-3.5 shrink-0 ${color}`} />
                    <div className="min-w-0 flex-1">
                      <p>{claim.claim_text}</p>
                      <p className="mt-0.5 text-muted-foreground">
                        {claim.filename}
                        {claim.page_number != null && `, p.${claim.page_number}`}
                        {" "}&middot;{" "}
                        <span
                          className={
                            claim.grounding_score >= 0.8
                              ? "font-medium text-green-600"
                              : claim.grounding_score >= 0.5
                                ? "font-medium text-yellow-600"
                                : "font-medium text-red-600"
                          }
                        >
                          {(claim.grounding_score * 100).toFixed(0)}%
                        </span>
                      </p>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Follow-up question chips */}
        {followUps.length > 0 && onFollowUpSelect && (
          <div className="flex flex-wrap gap-2 px-1">
            {followUps.map((q, idx) => (
              <button
                key={q}
                onClick={() => onFollowUpSelect(q)}
                className="animate-in fade-in slide-in-from-bottom-2 rounded-full border bg-background px-3 py-1.5 text-xs text-muted-foreground transition-colors duration-200 hover:bg-accent hover:text-accent-foreground"
                style={{ animationDelay: `${idx * 75}ms`, animationFillMode: "both" }}
              >
                {q}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
