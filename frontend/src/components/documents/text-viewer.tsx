import { useState, useEffect, useMemo } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { AlertCircle, ChevronLeft, ChevronRight } from "lucide-react";

const LINES_PER_PAGE = 80;

interface TextViewerProps {
  url: string;
  compact?: boolean;
}

export function TextViewer({ url, compact }: TextViewerProps) {
  const [content, setContent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pageNumber, setPageNumber] = useState(1);

  useEffect(() => {
    const controller = new AbortController();
    setContent(null);
    setError(null);
    setPageNumber(1);

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

  const { lines, numPages } = useMemo(() => {
    if (!content) return { lines: [], numPages: 0 };
    const allLines = content.split("\n");
    return { lines: allLines, numPages: Math.max(1, Math.ceil(allLines.length / LINES_PER_PAGE)) };
  }, [content]);

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

  const maxH = compact ? "max-h-[60vh]" : "";

  // Compact mode: no pagination, just scroll
  if (compact) {
    return (
      <div className={`overflow-y-auto rounded-md border bg-muted/30 ${maxH}`}>
        <pre className="whitespace-pre-wrap break-words p-4 text-sm leading-relaxed">
          {content}
        </pre>
      </div>
    );
  }

  const pageLines = lines.slice(
    (pageNumber - 1) * LINES_PER_PAGE,
    pageNumber * LINES_PER_PAGE,
  );

  return (
    <div className="flex h-full flex-col items-center gap-3">
      {numPages > 1 && (
        <div className="flex shrink-0 items-center gap-2">
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

      <div className={`w-full overflow-y-auto rounded-md border bg-muted/30 ${maxH} ${!compact ? "min-h-0 flex-1" : ""}`}>
        <pre className="whitespace-pre-wrap break-words p-4 text-sm leading-relaxed">
          {pageLines.join("\n")}
        </pre>
      </div>
    </div>
  );
}
