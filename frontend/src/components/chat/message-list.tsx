import { useRef, useEffect } from "react";
import { MessageSquare } from "lucide-react";
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

const EXAMPLE_QUERIES = [
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
}

interface MessageListProps {
  messages: ChatMessage[];
  streaming?: StreamingMessage | null;
  stage?: string | null;
  onExampleClick?: (query: string) => void;
}

export function MessageList({ messages, streaming, stage, onExampleClick }: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, streaming?.text]);

  return (
    <ScrollArea className="flex-1">
      <div className="mx-auto max-w-3xl space-y-6 px-4 py-6">
        {messages.length === 0 && !streaming && (
          <div className="flex min-h-[60vh] flex-1 flex-col items-center justify-center px-4 text-center">
            <div className="rounded-full bg-primary/10 p-4 mb-4">
              <MessageSquare className="h-8 w-8 text-primary" />
            </div>
            <h2 className="text-xl font-semibold tracking-tight">Start an Investigation</h2>
            <p className="mt-2 max-w-md text-sm text-muted-foreground">
              Ask questions about documents, entities, timelines, or communication patterns across your corpus.
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
