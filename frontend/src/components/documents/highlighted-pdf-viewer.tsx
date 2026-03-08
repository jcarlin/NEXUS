import { useState, useCallback, useEffect, useRef } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import { ChevronLeft, ChevronRight, ZoomIn, ZoomOut } from "lucide-react";
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

function normalizeText(s: string): string {
  return s.replace(/\s+/g, " ").trim().toLowerCase();
}

function applyHighlightToTextLayer(container: HTMLElement, highlightText: string) {
  const spans = container.querySelectorAll<HTMLSpanElement>(
    ".react-pdf__Page__textContent span",
  );
  if (spans.length === 0) return;

  // Build page text from spans
  const spanTexts: string[] = [];
  for (const span of spans) {
    spanTexts.push(span.textContent ?? "");
  }
  const fullText = spanTexts.join("");
  const normalizedFull = normalizeText(fullText);
  const normalizedSearch = normalizeText(highlightText.slice(0, 300));

  const matchIdx = normalizedFull.indexOf(normalizedSearch);
  if (matchIdx === -1) return;

  // Map normalized index back to original character positions
  let normIdx = 0;
  let origIdx = 0;
  const origText = fullText;

  // Find original start
  while (normIdx < matchIdx && origIdx < origText.length) {
    if (/\s/.test(origText[origIdx]!)) {
      while (origIdx < origText.length && /\s/.test(origText[origIdx]!)) origIdx++;
      normIdx++; // one space in normalized
    } else {
      origIdx++;
      normIdx++;
    }
  }
  const matchStartOrig = origIdx;

  // Find original end
  let matchEndNorm = matchIdx + normalizedSearch.length;
  while (normIdx < matchEndNorm && origIdx < origText.length) {
    if (/\s/.test(origText[origIdx]!)) {
      while (origIdx < origText.length && /\s/.test(origText[origIdx]!)) origIdx++;
      normIdx++;
    } else {
      origIdx++;
      normIdx++;
    }
  }
  const matchEndOrig = origIdx;

  // Map to spans: find which spans overlap [matchStartOrig, matchEndOrig)
  let charOffset = 0;
  for (const span of spans) {
    const text = span.textContent ?? "";
    const spanStart = charOffset;
    const spanEnd = charOffset + text.length;
    charOffset = spanEnd;

    if (spanEnd <= matchStartOrig || spanStart >= matchEndOrig) continue;

    // This span overlaps with the match
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
  const pageContainerRef = useRef<HTMLDivElement>(null);

  const onDocumentLoadSuccess = useCallback(({ numPages: n }: { numPages: number }) => {
    setNumPages(n);
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
        <Document file={url} onLoadSuccess={onDocumentLoadSuccess} loading={<div className="p-8 text-muted-foreground">Loading PDF...</div>}>
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
