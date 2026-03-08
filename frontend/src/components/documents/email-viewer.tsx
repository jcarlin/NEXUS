import { useState, useEffect, useMemo } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { AlertCircle, ChevronLeft, ChevronRight } from "lucide-react";

const LINES_PER_PAGE = 80;

interface EmailViewerProps {
  url: string;
  compact?: boolean;
}

interface ParsedEmail {
  headers: Record<string, string>;
  body: string;
}

const DISPLAY_HEADERS = ["From", "To", "Cc", "Subject", "Date"];

function parseEml(raw: string): ParsedEmail {
  // Split headers from body at first blank line
  const headerEnd = raw.search(/\r?\n\r?\n/);
  const headerBlock = headerEnd >= 0 ? raw.slice(0, headerEnd) : raw;
  const body = headerEnd >= 0 ? raw.slice(headerEnd).replace(/^[\r\n]+/, "") : "";

  // Unfold RFC 2822 continuation lines (leading whitespace)
  const unfolded = headerBlock.replace(/\r?\n[ \t]+/g, " ");
  const headers: Record<string, string> = {};

  for (const line of unfolded.split(/\r?\n/)) {
    const colonIdx = line.indexOf(":");
    if (colonIdx > 0) {
      const key = line.slice(0, colonIdx).trim();
      const value = line.slice(colonIdx + 1).trim();
      headers[key] = value;
    }
  }

  return { headers, body };
}

export function EmailViewer({ url, compact }: EmailViewerProps) {
  const [email, setEmail] = useState<ParsedEmail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pageNumber, setPageNumber] = useState(1);

  useEffect(() => {
    const controller = new AbortController();
    setEmail(null);
    setError(null);
    setPageNumber(1);

    fetch(url, { signal: controller.signal })
      .then((res) => {
        if (!res.ok) throw new Error(`Failed to load (${res.status})`);
        return res.text();
      })
      .then((raw) => setEmail(parseEml(raw)))
      .catch((err) => {
        if (err.name !== "AbortError") setError(err.message);
      });

    return () => controller.abort();
  }, [url]);

  const { lines, numPages } = useMemo(() => {
    if (!email) return { lines: [], numPages: 0 };
    const allLines = email.body.split("\n");
    return { lines: allLines, numPages: Math.max(1, Math.ceil(allLines.length / LINES_PER_PAGE)) };
  }, [email]);

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 rounded-md border p-8 text-muted-foreground">
        <AlertCircle className="h-8 w-8" />
        <p className="text-sm">{error}</p>
      </div>
    );
  }

  if (!email) {
    return <Skeleton className={compact ? "h-[300px]" : "h-[500px]"} />;
  }

  const maxH = compact ? "max-h-[60vh]" : "max-h-[calc(100vh-300px)]";

  const headerSection = (
    <div className="rounded-md border bg-muted/50 p-3 text-sm">
      {DISPLAY_HEADERS.map((key) => {
        const value = email.headers[key];
        if (!value) return null;
        return (
          <div key={key} className="flex gap-2">
            <span className="shrink-0 font-medium text-muted-foreground w-16">
              {key}:
            </span>
            <span className="break-all">{value}</span>
          </div>
        );
      })}
    </div>
  );

  // Compact mode: no pagination, just scroll
  if (compact) {
    return (
      <div className="space-y-3">
        {headerSection}
        <div className={`overflow-y-auto rounded-md border bg-muted/30 ${maxH}`}>
          <pre className="whitespace-pre-wrap break-words p-4 text-sm leading-relaxed">
            {email.body}
          </pre>
        </div>
      </div>
    );
  }

  const pageLines = lines.slice(
    (pageNumber - 1) * LINES_PER_PAGE,
    pageNumber * LINES_PER_PAGE,
  );

  return (
    <div className="space-y-3">
      {headerSection}

      <div className="flex flex-col items-center space-y-3">
        {numPages > 1 && (
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="icon"
              onClick={() => setPageNumber((p) => Math.max(1, p - 1))}
              disabled={pageNumber <= 1}
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <span className="text-sm text-muted-foreground">
              Page {pageNumber} of {numPages}
            </span>
            <Button
              variant="outline"
              size="icon"
              onClick={() => setPageNumber((p) => Math.min(numPages, p + 1))}
              disabled={pageNumber >= numPages}
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        )}

        <div className={`w-full overflow-y-auto rounded-md border bg-muted/30 ${maxH}`}>
          <pre className="whitespace-pre-wrap break-words p-4 text-sm leading-relaxed">
            {pageLines.join("\n")}
          </pre>
        </div>
      </div>
    </div>
  );
}
