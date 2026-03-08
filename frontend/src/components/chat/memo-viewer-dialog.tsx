import { useState, useCallback } from "react";
import { Copy, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import { MarkdownMessage } from "./markdown-message";
import type { MemoResponse } from "@/types";

interface MemoViewerDialogProps {
  memo: MemoResponse | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function MemoViewerDialog({ memo, open, onOpenChange }: MemoViewerDialogProps) {
  const [copied, setCopied] = useState(false);

  const fullText = memo
    ? memo.sections.map((s) => `## ${s.heading}\n\n${s.content}`).join("\n\n")
    : "";

  const handleCopy = useCallback(async () => {
    await navigator.clipboard.writeText(fullText);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [fullText]);

  if (!memo) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[80vh] flex flex-col">
        <DialogHeader>
          <DialogTitle>{memo.title}</DialogTitle>
          <DialogDescription className="sr-only">Generated legal memo</DialogDescription>
        </DialogHeader>
        <ScrollArea className="flex-1 pr-4">
          <div className="space-y-4">
            {memo.sections.map((section, idx) => (
              <div key={idx}>
                <h3 className="text-sm font-semibold mb-1">{section.heading}</h3>
                <div className="text-sm">
                  <MarkdownMessage content={section.content} sources={[]} />
                </div>
              </div>
            ))}
          </div>
        </ScrollArea>
        <DialogFooter>
          <Button variant="outline" size="sm" onClick={handleCopy} className="gap-1.5">
            {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
            {copied ? "Copied" : "Copy memo"}
          </Button>
          <Button size="sm" onClick={() => onOpenChange(false)}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
