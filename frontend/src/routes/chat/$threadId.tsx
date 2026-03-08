import { useCallback, useEffect, useRef } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { apiClient } from "@/api/client";
import { ChatLayout } from "@/components/chat/chat-layout";
import { ChatHeader } from "@/components/chat/chat-header";
import { MessageList } from "@/components/chat/message-list";
import { MessageInput } from "@/components/chat/message-input";
import { FindingsBar } from "@/components/chat/findings-bar";
import { useStreamQuery } from "@/hooks/use-stream-query";
import type { ChatMessage } from "@/types";

interface ThreadSearchParams {
  followUp?: string;
}

export const Route = createFileRoute("/chat/$threadId")({
  component: ChatThreadPage,
  validateSearch: (search: Record<string, unknown>): ThreadSearchParams => ({
    followUp: typeof search.followUp === "string" ? search.followUp : undefined,
  }),
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

  // Auto-send follow-up if provided via search params
  useEffect(() => {
    if (followUp && !isLoading && followUpSentRef.current !== followUp) {
      followUpSentRef.current = followUp;
      send(followUp);
    }
  }, [followUp, isLoading, send]);

  // Cache invalidation is handled by the stream store on `done` events —
  // no need for a prevStreaming ref here.

  const messages = data?.messages ?? [];
  const streamDone = !isStreaming && !!streamingText;

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
        <ChatHeader />
        <MessageList
          messages={messages}
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
          onFollowUpSelect={handleSend}
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
