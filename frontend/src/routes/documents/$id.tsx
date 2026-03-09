import { useState, useCallback } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Download } from "lucide-react";
import { apiClient } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { DocumentViewer } from "@/components/documents/document-viewer";
import { MetadataPanel } from "@/components/documents/metadata-panel";
import { AnnotationPanel } from "@/components/documents/annotation-panel";
import { RedactionPanel } from "@/components/documents/redaction-panel";
import { useAnnotations } from "@/hooks/use-annotations";
import { useDocumentDownload } from "@/hooks/use-document-download";
import { useFeatureFlag } from "@/hooks/use-feature-flags";
import { detectDocumentType } from "@/lib/utils";
import type { DocumentDetail, Annotation, AnnotationAnchor } from "@/types";

export const Route = createFileRoute("/documents/$id")({
  component: DocumentDetailPage,
});

function DocumentDetailPage() {
  const { id } = Route.useParams();

  const [selectedAnnotationId, setSelectedAnnotationId] = useState<string | null>(null);
  const [pendingAnchor, setPendingAnchor] = useState<{
    anchor: AnnotationAnchor;
    pageNumber: number;
  } | null>(null);

  const { data: doc, isLoading } = useQuery({
    queryKey: ["document", id],
    queryFn: () =>
      apiClient<DocumentDetail>({
        url: `/api/v1/documents/${id}`,
        method: "GET",
      }),
  });

  const { downloadUrl, filename: downloadFilename } = useDocumentDownload(doc ? id : null);

  const redactionEnabled = useFeatureFlag("redaction");
  const { data: annotationsData } = useAnnotations(id);
  const annotations = annotationsData?.items ?? [];
  const isPdf = doc ? detectDocumentType(doc.type, doc.filename) === "pdf" : false;

  const handleAnnotationClick = useCallback((annotation: Annotation) => {
    setSelectedAnnotationId(annotation.id);
  }, []);

  const handleCreateHighlight = useCallback(
    (anchor: AnnotationAnchor, pageNumber: number) => {
      setPendingAnchor({ anchor, pageNumber });
    },
    [],
  );

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-64" />
        <div className="grid grid-cols-3 gap-6">
          <div className="col-span-2">
            <Skeleton className="h-[600px]" />
          </div>
          <Skeleton className="h-[600px]" />
        </div>
      </div>
    );
  }

  if (!doc) {
    return <p className="text-muted-foreground">Document not found.</p>;
  }

  return (
    <div className="flex h-full flex-col gap-4">
      <div className="flex shrink-0 items-center justify-between">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="icon" asChild>
            <Link to="/documents">
              <ArrowLeft className="h-4 w-4" />
            </Link>
          </Button>
          <div>
            <h1 className="text-xl font-bold truncate max-w-lg">{doc.filename}</h1>
            <p className="text-sm text-muted-foreground">
              {doc.page_count} pages | {doc.chunk_count} chunks | {doc.entity_count} entities
            </p>
          </div>
        </div>
        {downloadUrl && (
          <Button variant="outline" size="sm" asChild>
            <a href={downloadUrl} download={downloadFilename ?? undefined}>
              <Download className="mr-2 h-3.5 w-3.5" />
              Download
            </a>
          </Button>
        )}
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="flex min-h-0 flex-col lg:col-span-2">
          {downloadUrl ? (
            <DocumentViewer
              url={downloadUrl}
              filename={doc.filename}
              type={doc.type}
              annotations={annotations}
              selectedAnnotationId={selectedAnnotationId}
              onAnnotationClick={handleAnnotationClick}
              onCreateHighlight={handleCreateHighlight}
            />
          ) : (
            <Skeleton className="h-[400px]" />
          )}
        </div>
        <div className="min-h-0 overflow-y-auto">
          {isPdf ? (
            <Tabs defaultValue="metadata">
              <TabsList className="w-full">
                <TabsTrigger value="metadata" className="flex-1">Metadata</TabsTrigger>
                <TabsTrigger value="annotations" className="flex-1">
                  Annotations ({annotations.length})
                </TabsTrigger>
                {redactionEnabled && (
                  <TabsTrigger value="redaction" className="flex-1">Redaction</TabsTrigger>
                )}
              </TabsList>
              <TabsContent value="metadata">
                <MetadataPanel doc={doc} />
              </TabsContent>
              <TabsContent value="annotations">
                <AnnotationPanel
                  documentId={id}
                  annotations={annotations}
                  selectedId={selectedAnnotationId}
                  onSelectAnnotation={handleAnnotationClick}
                  pendingAnchor={pendingAnchor}
                  onClearPending={() => setPendingAnchor(null)}
                />
              </TabsContent>
              {redactionEnabled && (
                <TabsContent value="redaction">
                  <RedactionPanel documentId={id} />
                </TabsContent>
              )}
            </Tabs>
          ) : (
            <MetadataPanel doc={doc} />
          )}
        </div>
      </div>
    </div>
  );
}
