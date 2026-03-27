import { useRef, useEffect, useState, useCallback } from "react";
import { MessageSquare, ChevronDown } from "lucide-react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Button } from "@/components/ui/button";
import { UserMessage } from "./user-message";
import { AssistantMessage } from "./assistant-message";
import { SmartActivityLog } from "./smart-activity-log";
import { ErrorMessage } from "./error-message";
import { ClarificationPrompt } from "./clarification-prompt";
import { FollowUpChips } from "./follow-up-chips";
import type {
  ChatMessage,
  SourceDocument,
  EntityMention,
  CitedClaim,
  ToolCallEntry,
  TraceStep,
  TraceSummary,
} from "@/types";

export const EXAMPLE_QUERIES = [
  "Who are the key parties in this matter?",
  "Summarize the timeline of events",
  "Which documents mention financial transactions?",
  "Find communications between executives",
];

interface StreamingMessage {
  text: string;
  sources: SourceDocument[];
  entities: EntityMention[];
  citedClaims: CitedClaim[];
  toolCalls: ToolCallEntry[];
  traceSteps: TraceStep[];
  traceSummary: TraceSummary | null;
}

interface MessageListProps {
  messages: ChatMessage[];
  streaming?: StreamingMessage | null;
  stage?: string | null;
  pendingUserMessage?: string | null;
  error?: string | null;
  onRetry?: () => void;
  followUps?: string[];
  onFollowUpSelect?: (query: string) => void;
  onExampleClick?: (query: string) => void;
  threadId?: string;
  clarificationQuestion?: string | null;
  onClarificationSubmit?: (answer: string) => void;
  isResuming?: boolean;
}

const SCROLL_THRESHOLD = 80;

export function MessageList({
  messages,
  streaming,
  stage,
  pendingUserMessage,
  error,
  onRetry,
  followUps,
  onFollowUpSelect,
  onExampleClick,
  threadId,
  clarificationQuestion,
  onClarificationSubmit,
  isResuming,
}: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const viewportRef = useRef<HTMLElement | null>(null);
  const scrollAreaRef = useRef<HTMLDivElement>(null);
  const [isAtBottom, setIsAtBottom] = useState(true);
  const [showScrollButton, setShowScrollButton] = useState(false);

  // Get viewport element from ScrollArea
  useEffect(() => {
    const el = scrollAreaRef.current?.querySelector("[data-radix-scroll-area-viewport]");
    if (el instanceof HTMLElement) {
      viewportRef.current = el;
    }
  }, []);

  // Track scroll position
  const handleScroll = useCallback(() => {
    const viewport = viewportRef.current;
    if (!viewport) return;
    const distanceFromBottom = viewport.scrollHeight - viewport.scrollTop - viewport.clientHeight;
    const atBottom = distanceFromBottom < SCROLL_THRESHOLD;
    setIsAtBottom(atBottom);
    setShowScrollButton(!atBottom);
  }, []);

  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport) return;
    viewport.addEventListener("scroll", handleScroll, { passive: true });
    return () => viewport.removeEventListener("scroll", handleScroll);
  }, [handleScroll]);

  // Auto-scroll only when user is at bottom
  useEffect(() => {
    if (isAtBottom) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages.length, streaming?.text, stage, pendingUserMessage, isAtBottom]);

  const scrollToBottom = useCallback(() => {
    setIsAtBottom(true);
    setShowScrollButton(false);
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  const hasContent = messages.length > 0 || streaming || pendingUserMessage;
  const showFollowUps = followUps && followUps.length > 0 && !streaming && !stage;

  return (
    <div className="relative flex-1">
      <ScrollArea className="h-full" ref={scrollAreaRef}>
        <div className="mx-auto max-w-3xl space-y-4 px-4 py-6">
          {!hasContent && (
            <div className="flex min-h-[60vh] flex-1 flex-col items-center justify-center px-4 text-center">
              <div className="rounded-full bg-primary/10 p-4 mb-4">
                <MessageSquare className="h-8 w-8 text-primary" />
              </div>
              <h2 className="text-xl font-semibold tracking-tight">Welcome to NEXUS</h2>
              <p className="mt-1 text-sm font-medium text-muted-foreground/80">Your legal investigation assistant</p>
              <p className="mt-2 max-w-md text-sm text-muted-foreground">
                Ask questions about documents, people, timelines, and communication patterns across your case.
              </p>
              {onExampleClick && (
                <div className="mt-6 flex flex-wrap justify-center gap-2">
                  {EXAMPLE_QUERIES.map((q) => (
                    <button
                      key={q}
                      type="button"
                      className="rounded-full border border-border bg-card px-4 py-2 text-sm transition-all duration-150 hover:bg-accent/60 hover:border-primary/30 active:scale-[0.97]"
                      onClick={() => onExampleClick(q)}
                    >
                      {q}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          {messages.map((msg, idx) =>
            msg.role === "user" ? (
              <UserMessage key={idx} content={msg.content} />
            ) : (
              <div key={idx}>
                {msg.tool_calls && msg.tool_calls.length > 0 && (
                  <div className="mb-2">
                    <SmartActivityLog toolCalls={msg.tool_calls} traceSteps={[]} traceSummary={null} stage={null} isStreaming={false} />
                  </div>
                )}
                <AssistantMessage
                  content={msg.content}
                  sources={msg.source_documents}
                  entities={msg.entities_mentioned}
                  citedClaims={msg.cited_claims}
                  threadId={threadId}
                />
              </div>
            ),
          )}

          {pendingUserMessage && <UserMessage content={pendingUserMessage} />}

          {(stage || (streaming?.toolCalls && streaming.toolCalls.length > 0)) && (
            <SmartActivityLog
              toolCalls={streaming?.toolCalls ?? []}
              traceSteps={streaming?.traceSteps ?? []}
              traceSummary={streaming?.traceSummary ?? null}
              stage={stage ?? null}
              isStreaming={!!stage}
            />
          )}

          {clarificationQuestion && onClarificationSubmit && (
            <ClarificationPrompt
              question={clarificationQuestion}
              onSubmit={onClarificationSubmit}
              isResuming={isResuming}
            />
          )}

          {streaming && streaming.text && (
            <AssistantMessage
              content={streaming.text}
              sources={streaming.sources}
              entities={streaming.entities}
              citedClaims={streaming.citedClaims}
              isStreaming
            />
          )}

          {error && onRetry && <ErrorMessage message={error} onRetry={onRetry} />}

          {showFollowUps && onFollowUpSelect && (
            <div className="pt-2">
              <FollowUpChips questions={followUps} onSelect={onFollowUpSelect} />
            </div>
          )}

          <div ref={bottomRef} />
        </div>
      </ScrollArea>

      {showScrollButton && (
        <div className="absolute bottom-4 left-1/2 -translate-x-1/2 z-10">
          <Button
            size="sm"
            variant="secondary"
            className="h-8 gap-1.5 rounded-full shadow-md text-xs"
            onClick={scrollToBottom}
          >
            <ChevronDown className="h-3.5 w-3.5" />
            New content
          </Button>
        </div>
      )}
    </div>
  );
}
