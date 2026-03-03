import { useCallback } from "react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useQueryClient } from "@tanstack/react-query";
import { ThreadSidebar } from "@/components/chat/thread-sidebar";
import { MessageList } from "@/components/chat/message-list";
import { MessageInput } from "@/components/chat/message-input";
import { FollowUpChips } from "@/components/chat/follow-up-chips";
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
    send,
  } = useStreamQuery();

  const handleSend = useCallback(
    (text: string) => {
      send(text);
    },
    [send],
  );

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
    <div className="-m-6 flex h-[calc(100vh-3.5rem)] overflow-hidden">
      <ThreadSidebar />

      <div className="flex flex-1 flex-col">
        <MessageList
          messages={[]}
          streaming={
            streamingText || isStreaming
              ? { text: streamingText, sources, entities, citedClaims }
              : null
          }
          stage={stage}
          onExampleClick={handleSend}
        />

        {streamDone && followUps.length > 0 && (
          <div className="border-t px-4 py-2">
            <FollowUpChips questions={followUps} onSelect={handleFollowUp} />
          </div>
        )}

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
        <MessageInput onSend={handleSend} disabled={isStreaming} />
      </div>
    </div>
  );
}
