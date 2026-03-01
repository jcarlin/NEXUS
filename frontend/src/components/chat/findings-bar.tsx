import { useState } from "react";
import {
  ChevronDown,
  ChevronUp,
  X,
  BookmarkCheck,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useAppStore } from "@/stores/app-store";

export function FindingsBar() {
  const [open, setOpen] = useState(false);
  const findings = useAppStore((s) => s.findings);
  const removeFinding = useAppStore((s) => s.removeFinding);
  const clearFindings = useAppStore((s) => s.clearFindings);

  if (findings.length === 0) return null;

  return (
    <div className="border-t bg-muted/30">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between px-4 py-2 text-sm font-medium hover:bg-accent"
      >
        <span className="flex items-center gap-2">
          <BookmarkCheck className="h-4 w-4" />
          Findings
          <Badge variant="secondary" className="text-[10px]">
            {findings.length}
          </Badge>
        </span>
        {open ? (
          <ChevronDown className="h-4 w-4" />
        ) : (
          <ChevronUp className="h-4 w-4" />
        )}
      </button>

      {open && (
        <div className="max-h-48 space-y-1 overflow-y-auto px-4 pb-3">
          {findings.map((claim, idx) => (
            <div
              key={idx}
              className="flex items-start gap-2 rounded-md border bg-background px-3 py-2 text-xs"
            >
              <div className="min-w-0 flex-1">
                <p>{claim.claim_text}</p>
                <p className="mt-0.5 text-muted-foreground">
                  {claim.filename}
                  {claim.page_number != null && `, p.${claim.page_number}`}
                </p>
              </div>
              <Button
                variant="ghost"
                size="sm"
                className="h-5 w-5 shrink-0 p-0"
                onClick={() => removeFinding(idx)}
              >
                <X className="h-3 w-3" />
              </Button>
            </div>
          ))}
          <Button
            variant="ghost"
            size="sm"
            className="mt-1 text-xs text-destructive"
            onClick={clearFindings}
          >
            Clear all findings
          </Button>
        </div>
      )}
    </div>
  );
}
