import { useState, useCallback, useEffect, useRef } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import { ChevronLeft, ChevronRight, ZoomIn, ZoomOut, FileWarning, Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import { AnnotationLayer } from "@/components/documents/annotation-layer";
import type { Annotation, AnnotationAnchor } from "@/types";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url,
).toString();

interface HighlightedPdfViewerProps {
  url: string;
  initialPage?: number;
  highlightText?: string;
  annotations?: Annotation[];
  selectedAnnotationId?: string | null;
  onAnnotationClick?: (annotation: Annotation) => void;
  onCreateHighlight?: (anchor: AnnotationAnchor, pageNumber: number) => void;
}

function stripForMatch(s: string): string {
  return s.replace(/\s+/g, "").toLowerCase();
}

function applyHighlightToTextLayer(container: HTMLElement, highlightText: string) {
  const spans = container.querySelectorAll<HTMLSpanElement>(
    ".react-pdf__Page__textContent span",
  );
  if (spans.length === 0) return;

  // Strip all whitespace for matching — PDF text layer spans often lack
  // inter-word spaces, so whitespace-aware matching fails silently.
  const strippedFull = stripForMatch(
    Array.from(spans, (s) => s.textContent ?? "").join(" "),
  );
  const strippedSearch = stripForMatch(highlightText.slice(0, 300));

  let matchIdx = strippedFull.indexOf(strippedSearch);
  // Fallback: try shorter prefix if full match fails (chunk may span pages)
  if (matchIdx === -1 && strippedSearch.length > 80) {
    const shorter = strippedSearch.slice(0, 80);
    matchIdx = strippedFull.indexOf(shorter);
  }
  if (matchIdx === -1) return;

  const matchEnd = matchIdx + strippedSearch.length;

  // Map stripped character positions back to spans
  let strippedCount = 0;
  for (const span of spans) {
    const text = span.textContent ?? "";
    const spanStrippedStart = strippedCount;
    const strippedLen = text.replace(/\s+/g, "").length;
    strippedCount += strippedLen;

    if (strippedCount <= matchIdx || spanStrippedStart >= matchEnd) continue;

    span.classList.add("citation-highlight");
  }
}

export function HighlightedPdfViewer({
  url,
  initialPage = 1,
  highlightText,
  annotations,
  selectedAnnotationId,
  onAnnotationClick,
  onCreateHighlight,
}: HighlightedPdfViewerProps) {
  const [numPages, setNumPages] = useState<number>(0);
  const [pageNumber, setPageNumber] = useState(initialPage);
  const [scale, setScale] = useState(1.0);
  const [error, setError] = useState<string | null>(null);
  const pageContainerRef = useRef<HTMLDivElement>(null);

  const onDocumentLoadSuccess = useCallback(({ numPages: n }: { numPages: number }) => {
    setNumPages(n);
    setError(null);
  }, []);

  const onDocumentLoadError = useCallback((err: Error) => {
    console.error("PDF load error:", err);
    setError("Failed to load PDF preview. The file may be too large or corrupted.");
  }, []);

  // Reset page when initialPage changes (source navigation)
  useEffect(() => {
    setPageNumber(initialPage);
  }, [initialPage]);

  const handleTextLayerRendered = useCallback(() => {
    if (!highlightText || !pageContainerRef.current) return;
    requestAnimationFrame(() => {
      if (pageContainerRef.current) {
        applyHighlightToTextLayer(pageContainerRef.current, highlightText);
        const highlighted = pageContainerRef.current.querySelector(".citation-highlight");
        if (highlighted) {
          highlighted.scrollIntoView({ behavior: "smooth", block: "center" });
        }
      }
    });
  }, [highlightText]);

  // Re-apply highlighting when scale changes
  useEffect(() => {
    if (!highlightText || !pageContainerRef.current) return;
    const timer = setTimeout(() => {
      if (pageContainerRef.current) {
        // Clear previous highlights
        const prev = pageContainerRef.current.querySelectorAll(".citation-highlight");
        prev.forEach((el) => el.classList.remove("citation-highlight"));
        applyHighlightToTextLayer(pageContainerRef.current, highlightText);
        const highlighted = pageContainerRef.current.querySelector(".citation-highlight");
        if (highlighted) {
          highlighted.scrollIntoView({ behavior: "smooth", block: "center" });
        }
      }
    }, 200);
    return () => clearTimeout(timer);
  }, [scale, highlightText]);

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 rounded-md border p-12 text-muted-foreground">
        <FileWarning className="h-12 w-12" />
        <p className="text-sm">{error}</p>
        <Button variant="outline" size="sm" asChild>
          <a href={url} download>
            <Download className="mr-2 h-3.5 w-3.5" />
            Download instead
          </a>
        </Button>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col items-center gap-3">
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
          Page {pageNumber} of {numPages || "..."}
        </span>
        <Button
          variant="outline"
          size="icon"
          onClick={() => setPageNumber((p) => Math.min(numPages, p + 1))}
          disabled={pageNumber >= numPages}
        >
          <ChevronRight className="h-4 w-4" />
        </Button>
        <div className="ml-4 flex items-center gap-1">
          <Button variant="outline" size="icon" onClick={() => setScale((s) => Math.max(0.5, s - 0.25))}>
            <ZoomOut className="h-4 w-4" />
          </Button>
          <span className="w-12 text-center text-xs text-muted-foreground">{Math.round(scale * 100)}%</span>
          <Button variant="outline" size="icon" onClick={() => setScale((s) => Math.min(3, s + 0.25))}>
            <ZoomIn className="h-4 w-4" />
          </Button>
        </div>
      </div>

      <div className="min-h-0 w-full flex-1 overflow-auto rounded border bg-muted/30">
        <Document file={url} onLoadSuccess={onDocumentLoadSuccess} onLoadError={onDocumentLoadError} loading={<div className="p-8 text-muted-foreground">Loading PDF...</div>}>
          <div ref={pageContainerRef} className="relative">
            <Page
              pageNumber={pageNumber}
              scale={scale}
              onRenderTextLayerSuccess={handleTextLayerRendered}
            />
            {annotations && (
              <AnnotationLayer
                pageNumber={pageNumber}
                annotations={annotations}
                selectedId={selectedAnnotationId}
                onAnnotationClick={onAnnotationClick}
                onCreateHighlight={onCreateHighlight}
              />
            )}
          </div>
        </Document>
      </div>
    </div>
  );
}
