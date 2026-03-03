import { detectDocumentType } from "@/lib/utils";
import { PdfViewer } from "./pdf-viewer";
import { TextViewer } from "./text-viewer";
import { ImageViewer } from "./image-viewer";
import { EmailViewer } from "./email-viewer";
import { UnsupportedViewer } from "./unsupported-viewer";
import type { Annotation, AnnotationAnchor } from "@/types";

interface DocumentViewerProps {
  url: string;
  filename: string;
  type?: string | null;
  compact?: boolean;
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
  annotations,
  selectedAnnotationId,
  onAnnotationClick,
  onCreateHighlight,
}: DocumentViewerProps) {
  const viewType = detectDocumentType(type, filename);

  switch (viewType) {
    case "pdf":
      return (
        <PdfViewer
          url={url}
          annotations={annotations}
          selectedAnnotationId={selectedAnnotationId}
          onAnnotationClick={onAnnotationClick}
          onCreateHighlight={onCreateHighlight}
        />
      );
    case "text":
      return <TextViewer url={url} compact={compact} />;
    case "image":
      return <ImageViewer url={url} filename={filename} compact={compact} />;
    case "email":
      return <EmailViewer url={url} compact={compact} />;
    default:
      return <UnsupportedViewer filename={filename} downloadUrl={url} type={type} />;
  }
}
