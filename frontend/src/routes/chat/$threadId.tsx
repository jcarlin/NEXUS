import { useCallback, useEffect, useRef } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { apiClient } from "@/api/client";
import { ChatLayout } from "@/components/chat/chat-layout";
import { MessageList } from "@/components/chat/message-list";
import { MessageInput } from "@/components/chat/message-input";
import { FollowUpChips } from "@/components/chat/follow-up-chips";
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
  const queryClient = useQueryClient();
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
    send,
  } = useStreamQuery();

  const handleSend = useCallback(
    (text: string) => {
      send(text, threadId);
    },
    [send, threadId],
  );

  // Auto-send follow-up if provided via search params
  useEffect(() => {
    if (followUp && !isLoading && followUpSentRef.current !== followUp) {
      followUpSentRef.current = followUp;
      send(followUp, threadId);
    }
  }, [followUp, isLoading, send, threadId]);

  // Refetch thread after streaming completes
  const prevStreaming = useRef(isStreaming);
  useEffect(() => {
    if (prevStreaming.current && !isStreaming) {
      void queryClient.invalidateQueries({
        queryKey: ["chat-thread", threadId],
      });
      void queryClient.invalidateQueries({ queryKey: ["chat-threads"] });
    }
    prevStreaming.current = isStreaming;
  }, [isStreaming, threadId, queryClient]);

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
        <MessageList
          messages={messages}
          streaming={
            streamingText || isStreaming
              ? { text: streamingText, sources, entities, citedClaims }
              : null
          }
          stage={stage}
        />

        {streamDone && followUps.length > 0 && (
          <div className="border-t px-4 py-2">
            <FollowUpChips
              questions={followUps}
              onSelect={handleSend}
            />
          </div>
        )}

        <FindingsBar />
        <MessageInput onSend={handleSend} disabled={isStreaming} />
      </div>
    </ChatLayout>
  );
}
