import { useState, useEffect, useRef, useCallback } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { AlertCircle } from "lucide-react";

interface HighlightedTextViewerProps {
  url: string;
  highlightText?: string;
  compact?: boolean;
}

function normalizeWhitespace(s: string): string {
  return s.replace(/\s+/g, " ").trim();
}

function findBestMatch(
  content: string,
  search: string,
): { start: number; end: number } | null {
  // Try exact match first
  const idx = content.indexOf(search);
  if (idx !== -1) return { start: idx, end: idx + search.length };

  // Try case-insensitive
  const lowerContent = content.toLowerCase();
  const lowerSearch = search.toLowerCase();
  const ciIdx = lowerContent.indexOf(lowerSearch);
  if (ciIdx !== -1) return { start: ciIdx, end: ciIdx + search.length };

  // Try whitespace-normalized matching
  const normContent = normalizeWhitespace(content);
  const normSearch = normalizeWhitespace(search);
  const normIdx = normContent.toLowerCase().indexOf(normSearch.toLowerCase());
  if (normIdx !== -1) {
    // Map back to original content position (approximate)
    // Walk through original content to find corresponding position
    let origPos = 0;
    let normPos = 0;
    while (normPos < normIdx && origPos < content.length) {
      if (/\s/.test(content[origPos]!)) {
        // Skip whitespace runs in original
        while (origPos < content.length && /\s/.test(content[origPos]!)) origPos++;
        normPos++; // Normalized has single space
      } else {
        origPos++;
        normPos++;
      }
    }
    const matchStart = origPos;
    // Advance through matched portion
    let matchLen = 0;
    while (normPos < normIdx + normSearch.length && origPos < content.length) {
      if (/\s/.test(content[origPos]!)) {
        while (origPos < content.length && /\s/.test(content[origPos]!)) {
          origPos++;
          matchLen++;
        }
        normPos++;
      } else {
        origPos++;
        matchLen++;
        normPos++;
      }
    }
    return { start: matchStart, end: matchStart + matchLen };
  }

  // Try matching first ~300 chars for long texts
  if (search.length > 300) {
    const shortSearch = search.slice(0, 300);
    return findBestMatch(content, shortSearch);
  }

  return null;
}

export function HighlightedTextViewer({
  url,
  highlightText,
  compact,
}: HighlightedTextViewerProps) {
  const [content, setContent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const markRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const controller = new AbortController();
    setContent(null);
    setError(null);

    fetch(url, { signal: controller.signal })
      .then((res) => {
        if (!res.ok) throw new Error(`Failed to load (${res.status})`);
        return res.text();
      })
      .then(setContent)
      .catch((err) => {
        if (err.name !== "AbortError") setError(err.message);
      });

    return () => controller.abort();
  }, [url]);

  const scrollToHighlight = useCallback(() => {
    if (markRef.current) {
      markRef.current.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, []);

  useEffect(() => {
    if (content && highlightText) {
      // Delay to ensure DOM is rendered
      const timer = setTimeout(scrollToHighlight, 100);
      return () => clearTimeout(timer);
    }
  }, [content, highlightText, scrollToHighlight]);

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 rounded-md border p-8 text-muted-foreground">
        <AlertCircle className="h-8 w-8" />
        <p className="text-sm">{error}</p>
      </div>
    );
  }

  if (content === null) {
    return <Skeleton className={compact ? "h-[300px]" : "h-[500px]"} />;
  }

  const maxH = compact ? "max-h-[60vh]" : "max-h-[calc(100vh-300px)]";
  const match = highlightText ? findBestMatch(content, highlightText) : null;

  return (
    <ScrollArea className={`rounded-md border bg-muted/30 ${maxH}`}>
      <pre className="whitespace-pre-wrap break-words p-4 text-sm leading-relaxed">
        {match ? (
          <>
            {content.slice(0, match.start)}
            <mark ref={markRef} className="citation-highlight">
              {content.slice(match.start, match.end)}
            </mark>
            {content.slice(match.end)}
          </>
        ) : (
          content
        )}
      </pre>
    </ScrollArea>
  );
}
