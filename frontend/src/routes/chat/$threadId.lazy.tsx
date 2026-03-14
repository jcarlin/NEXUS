import { useCallback, useEffect, useRef } from "react";
import { createLazyFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { apiClient } from "@/api/client";
import { ChatLayout } from "@/components/chat/chat-layout";
import { MessageList } from "@/components/chat/message-list";
import { MessageInput } from "@/components/chat/message-input";
import { FindingsBar } from "@/components/chat/findings-bar";
import { useStreamQuery } from "@/hooks/use-stream-query";
import type { ChatMessage } from "@/types";

export const Route = createLazyFileRoute("/chat/$threadId")({
  component: ChatThreadPage,
});

function ChatThreadPage() {
  const { threadId } = Route.useParams();
  const { followUp } = Route.useSearch();
  const followUpSentRef = useRef<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["chat-thread", threadId],
    queryFn: () =>
      apiClient<{ thread_id: string; messages: ChatMessage[] }>({
        url: `/api/v1/chats/${threadId}`,
        method: "GET",
      }),
  });

  const {
    streamingText,
    sources,
    stage,
    isStreaming,
    citedClaims,
    entities,
    followUps,
    pendingUserMessage,
    error,
    lastQuery,
    send,
    cancel,
  } = useStreamQuery(threadId);

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

  useEffect(() => {
    if (followUp && !isLoading && followUpSentRef.current !== followUp) {
      followUpSentRef.current = followUp;
      send(followUp);
    }
  }, [followUp, isLoading, send]);

  const messages = data?.messages ?? [];
  const streamDone = !isStreaming && !!streamingText;

  const lastMsg = messages[messages.length - 1];
  const dbHasCaughtUp =
    streamDone && lastMsg?.role === "assistant" && !!lastMsg.content;

  if (isLoading) {
    return (
      <ChatLayout>
        <div className="flex h-full items-center justify-center">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      </ChatLayout>
    );
  }

  return (
    <ChatLayout>
      <div className="flex h-full flex-col">
        <MessageList
          messages={messages}
          streaming={
            (streamingText || isStreaming) && !dbHasCaughtUp
              ? { text: streamingText, sources, entities, citedClaims }
              : null
          }
          stage={stage}
          pendingUserMessage={pendingUserMessage}
          error={error}
          onRetry={handleRetry}
          followUps={streamDone ? followUps : undefined}
          onFollowUpSelect={handleSend}
          threadId={threadId}
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
