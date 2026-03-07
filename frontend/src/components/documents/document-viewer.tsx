import { detectDocumentType } from "@/lib/utils";
import { PdfViewer } from "./pdf-viewer";
import { HighlightedPdfViewer } from "./highlighted-pdf-viewer";
import { TextViewer } from "./text-viewer";
import { HighlightedTextViewer } from "./highlighted-text-viewer";
import { ImageViewer } from "./image-viewer";
import { EmailViewer } from "./email-viewer";
import { UnsupportedViewer } from "./unsupported-viewer";
import type { Annotation, AnnotationAnchor } from "@/types";

interface DocumentViewerProps {
  url: string;
  filename: string;
  type?: string | null;
  compact?: boolean;
  initialPage?: number;
  highlightText?: string;
  // PDF-specific pass-through props
  annotations?: Annotation[];
  selectedAnnotationId?: string | null;
  onAnnotationClick?: (annotation: Annotation) => void;
  onCreateHighlight?: (anchor: AnnotationAnchor, pageNumber: number) => void;
}

export function DocumentViewer({
  url,
  filename,
  type,
  compact,
  initialPage,
  highlightText,
  annotations,
  selectedAnnotationId,
  onAnnotationClick,
  onCreateHighlight,
}: DocumentViewerProps) {
  const viewType = detectDocumentType(type, filename);

  switch (viewType) {
    case "pdf":
      return highlightText ? (
        <HighlightedPdfViewer
          url={url}
          initialPage={initialPage}
          highlightText={highlightText}
          annotations={annotations}
          selectedAnnotationId={selectedAnnotationId}
          onAnnotationClick={onAnnotationClick}
          onCreateHighlight={onCreateHighlight}
        />
      ) : (
        <PdfViewer
          url={url}
          initialPage={initialPage}
          annotations={annotations}
          selectedAnnotationId={selectedAnnotationId}
          onAnnotationClick={onAnnotationClick}
          onCreateHighlight={onCreateHighlight}
        />
      );
    case "text":
      return highlightText ? (
        <HighlightedTextViewer url={url} highlightText={highlightText} compact={compact} />
      ) : (
        <TextViewer url={url} compact={compact} />
      );
    case "image":
      return <ImageViewer url={url} filename={filename} compact={compact} />;
    case "email":
      return highlightText ? (
        <HighlightedTextViewer url={url} highlightText={highlightText} compact={compact} />
      ) : (
        <EmailViewer url={url} compact={compact} />
      );
    default:
      return <UnsupportedViewer filename={filename} downloadUrl={url} type={type} />;
  }
}
