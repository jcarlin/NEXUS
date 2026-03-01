import { useRef, useEffect } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { UserMessage } from "./user-message";
import { AssistantMessage } from "./assistant-message";
import { StageIndicator } from "./stage-indicator";
import type {
  ChatMessage,
  SourceDocument,
  EntityMention,
  CitedClaim,
} from "@/types";

interface StreamingMessage {
  text: string;
  sources: SourceDocument[];
  entities: EntityMention[];
  citedClaims: CitedClaim[];
}

interface MessageListProps {
  messages: ChatMessage[];
  streaming?: StreamingMessage | null;
  stage?: string | null;
}

export function MessageList({ messages, streaming, stage }: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, streaming?.text]);

  return (
    <ScrollArea className="flex-1">
      <div className="mx-auto max-w-3xl space-y-4 px-4 py-6">
        {messages.length === 0 && !streaming && (
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <p className="text-lg font-medium text-muted-foreground">
              Start an investigation query
            </p>
            <p className="mt-1 text-sm text-muted-foreground/70">
              Ask questions about documents, entities, timelines, or patterns.
            </p>
          </div>
        )}

        {messages.map((msg, idx) =>
          msg.role === "user" ? (
            <UserMessage key={idx} content={msg.content} />
          ) : (
            <AssistantMessage
              key={idx}
              content={msg.content}
              sources={msg.source_documents}
              entities={msg.entities_mentioned}
            />
          ),
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

        {stage && !streaming?.text && <StageIndicator stage={stage} />}

        <div ref={bottomRef} />
      </div>
    </ScrollArea>
  );
}
