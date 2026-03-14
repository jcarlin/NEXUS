import { useState, useCallback, type ChangeEvent, type KeyboardEvent } from "react";
import { HelpCircle, Send, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

interface ClarificationPromptProps {
  question: string;
  onSubmit: (answer: string) => void;
  isResuming?: boolean;
}

export function ClarificationPrompt({
  question,
  onSubmit,
  isResuming = false,
}: ClarificationPromptProps) {
  const [answer, setAnswer] = useState("");

  const handleSubmit = useCallback(() => {
    const trimmed = answer.trim();
    if (!trimmed || isResuming) return;
    onSubmit(trimmed);
  }, [answer, isResuming, onSubmit]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSubmit();
      }
    },
    [handleSubmit],
  );

  return (
    <div className="flex justify-start">
      <div className="max-w-[85%] space-y-3 rounded-2xl border border-primary/20 bg-primary/5 px-4 py-3">
        <div className="flex items-start gap-2">
          <HelpCircle className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
          <p className="text-sm leading-relaxed">{question}</p>
        </div>
        <div className="flex gap-2">
          <Textarea
            value={answer}
            onChange={(e: ChangeEvent<HTMLTextAreaElement>) => setAnswer(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type your answer..."
            disabled={isResuming}
            className="min-h-[40px] resize-none text-sm"
            rows={1}
          />
          <Button
            size="sm"
            onClick={handleSubmit}
            disabled={!answer.trim() || isResuming}
            className="shrink-0 self-end"
          >
            {isResuming ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
          </Button>
        </div>
      </div>
    </div>
  );
}
