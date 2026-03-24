import { useCallback, useEffect, useRef } from "react";
import { createLazyFileRoute, useNavigate } from "@tanstack/react-router";
import { MessageSquare } from "lucide-react";
import { ChatLayout } from "@/components/chat/chat-layout";
import { MessageList, EXAMPLE_QUERIES } from "@/components/chat/message-list";
import { MessageInput } from "@/components/chat/message-input";
import { FindingsBar } from "@/components/chat/findings-bar";
import { useStreamQuery } from "@/hooks/use-stream-query";

export const Route = createLazyFileRoute("/chat/")({
  component: ChatPage,
});

function ChatPage() {
  const navigate = useNavigate();
  const {
    streamingText,
    sources,
    stage,
    isStreaming,
    citedClaims,
    entities,
    followUps,
    toolCalls,
    threadId,
    pendingUserMessage,
    error,
    lastQuery,
    send,
    cancel,
  } = useStreamQuery();

  const sentRef = useRef(false);
  const handleSend = useCallback(
    (text: string) => {
      sentRef.current = true;
      send(text);
    },
    [send],
  );

  const handleRetry = useCallback(() => {
    if (lastQuery) {
      sentRef.current = true;
      send(lastQuery);
    }
  }, [lastQuery, send]);

  // Auto-navigate to thread page once stream completes with a threadId
  const navigatedRef = useRef<string | null>(null);
  useEffect(() => {
    if (sentRef.current && !isStreaming && threadId && navigatedRef.current !== threadId) {
      navigatedRef.current = threadId;
      void navigate({
        to: "/chat/$threadId",
        params: { threadId },
      });
    }
  }, [isStreaming, threadId, navigate]);

  // Navigate to thread page once stream completes and we have a thread ID
  const handleFollowUp = useCallback(
    (question: string) => {
      if (sentRef.current && threadId) {
        void navigate({
          to: "/chat/$threadId",
          params: { threadId },
          search: { followUp: question },
        });
      } else {
        sentRef.current = true;
        send(question);
      }
    },
    [threadId, navigate, send],
  );

  const hasContent = !!pendingUserMessage || !!streamingText || isStreaming;
  const streamDone = !isStreaming && !!streamingText;

  return (
    <ChatLayout>
      {!hasContent ? (
        <div className="flex h-full flex-col items-center justify-center px-4">
          <div className="w-full max-w-2xl">
            <div className="mb-8 flex flex-col items-center text-center">
              <div className="mb-4 rounded-full bg-primary/10 p-4">
                <MessageSquare className="h-8 w-8 text-primary" />
              </div>
              <h2 className="text-xl font-semibold tracking-tight">Welcome to NEXUS</h2>
              <p className="mt-1 text-sm font-medium text-muted-foreground/80">
                Your legal investigation assistant
              </p>
              <p className="mt-2 max-w-md text-sm text-muted-foreground">
                Ask questions about documents, people, timelines, and communication patterns
                across your case.
              </p>
            </div>
            <div className="mb-6 flex flex-wrap justify-center gap-2">
              {EXAMPLE_QUERIES.map((q) => (
                <button
                  key={q}
                  type="button"
                  className="rounded-full border border-border bg-card px-4 py-2 text-sm transition-all duration-150 hover:border-primary/30 hover:bg-accent/60 active:scale-[0.97]"
                  onClick={() => handleSend(q)}
                >
                  {q}
                </button>
              ))}
            </div>
            <MessageInput
              onSend={handleSend}
              onStop={cancel}
              isStreaming={isStreaming}
              disabled={isStreaming}
              variant="standalone"
            />
          </div>
        </div>
      ) : (
        <div className="flex h-full flex-col">
          <MessageList
            messages={[]}
            streaming={
              streamingText || isStreaming
                ? { text: streamingText, sources, entities, citedClaims, toolCalls }
                : null
            }
            stage={stage}
            pendingUserMessage={pendingUserMessage}
            error={error}
            onRetry={handleRetry}
            followUps={streamDone ? followUps : undefined}
            onFollowUpSelect={handleFollowUp}
            onExampleClick={handleSend}
          />

          <FindingsBar />
          <MessageInput
            onSend={handleSend}
            onStop={cancel}
            isStreaming={isStreaming}
            disabled={isStreaming}
          />
        </div>
      )}
    </ChatLayout>
  );
}
