import { useCallback, useEffect, useRef } from "react";
import { createLazyFileRoute, useNavigate } from "@tanstack/react-router";
import { motion } from "motion/react";
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
    traceSteps,
    traceSummary,
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
        <div className="flex h-full flex-col items-center justify-center px-4 pb-16">
          <motion.div
            className="w-full max-w-2xl"
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
          >
            <h2 className="mb-2 text-center text-lg font-medium tracking-tight text-muted-foreground">
              What would you like to investigate?
            </h2>
            <p className="mb-5 text-center text-sm text-muted-foreground/60">
              Ask about documents, people, timelines, and communication patterns across your case.
            </p>

            <MessageInput
              onSend={handleSend}
              onStop={cancel}
              isStreaming={isStreaming}
              disabled={isStreaming}
              variant="hero"
              threadId={undefined}
            />

            <div className="mt-4 flex flex-wrap justify-center gap-2">
              {EXAMPLE_QUERIES.map((q, i) => (
                <motion.button
                  key={q}
                  type="button"
                  className="rounded-full border border-border/50 px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:border-primary/30 hover:bg-accent/40 hover:text-foreground"
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.3, delay: 0.3 + i * 0.05, ease: [0.16, 1, 0.3, 1] }}
                  whileHover={{ scale: 1.04 }}
                  whileTap={{ scale: 0.97 }}
                  onClick={() => handleSend(q)}
                >
                  {q}
                </motion.button>
              ))}
            </div>
          </motion.div>
        </div>
      ) : (
        <div className="flex h-full flex-col">
          <MessageList
            messages={[]}
            streaming={
              streamingText || isStreaming
                ? { text: streamingText, sources, entities, citedClaims, toolCalls, traceSteps, traceSummary }
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
