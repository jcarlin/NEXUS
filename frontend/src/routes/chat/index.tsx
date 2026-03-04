import { useCallback } from "react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useQueryClient } from "@tanstack/react-query";
import { ChatLayout } from "@/components/chat/chat-layout";
import { MessageList } from "@/components/chat/message-list";
import { MessageInput } from "@/components/chat/message-input";
import { FindingsBar } from "@/components/chat/findings-bar";
import { useStreamQuery } from "@/hooks/use-stream-query";

export const Route = createFileRoute("/chat/")({
  component: ChatPage,
});

function ChatPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
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

  // If streaming is done and we got a threadId, offer navigation
  const streamDone = !isStreaming && !!streamingText;

  return (
    <ChatLayout>
      <div className="flex h-full flex-col">
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

        {streamDone && threadId && (
          <div className="flex items-center justify-center border-t px-4 py-2">
            <button
              onClick={() => {
                void queryClient.invalidateQueries({ queryKey: ["chat-threads"] });
                void navigate({
                  to: "/chat/$threadId",
                  params: { threadId },
                });
              }}
              className="text-xs text-primary hover:underline"
            >
              Continue this conversation
            </button>
          </div>
        )}

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
