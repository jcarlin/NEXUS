import { useCallback, useEffect, useRef } from "react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { ChatLayout } from "@/components/chat/chat-layout";
import { ChatHeader } from "@/components/chat/chat-header";
import { MessageList } from "@/components/chat/message-list";
import { MessageInput } from "@/components/chat/message-input";
import { FindingsBar } from "@/components/chat/findings-bar";
import { useStreamQuery } from "@/hooks/use-stream-query";

export const Route = createFileRoute("/chat/")({
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
    threadId,
    pendingUserMessage,
    error,
    lastQuery,
    send,
    cancel,
  } = useStreamQuery();

  const handleSend = useCallback(
    (text: string) => {
      send(text);
    },
    [send],
  );

  const handleRetry = useCallback(() => {
    if (lastQuery) {
      send(lastQuery);
    }
  }, [lastQuery, send]);

  // Auto-navigate to thread page once stream completes with a threadId
  const navigatedRef = useRef<string | null>(null);
  useEffect(() => {
    if (!isStreaming && threadId && navigatedRef.current !== threadId) {
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
      if (threadId) {
        void navigate({
          to: "/chat/$threadId",
          params: { threadId },
          search: { followUp: question },
        });
      } else {
        send(question);
      }
    },
    [threadId, navigate, send],
  );

  const streamDone = !isStreaming && !!streamingText;

  return (
    <ChatLayout>
      <div className="flex h-full flex-col">
        <ChatHeader />
        <MessageList
          messages={[]}
          streaming={
            streamingText || isStreaming
              ? { text: streamingText, sources, entities, citedClaims }
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
    </ChatLayout>
  );
}
