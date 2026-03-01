import { useState, useCallback } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Download } from "lucide-react";
import { apiClient } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { PdfViewer } from "@/components/documents/pdf-viewer";
import { MetadataPanel } from "@/components/documents/metadata-panel";
import { AnnotationPanel } from "@/components/documents/annotation-panel";
import { useAnnotations } from "@/hooks/use-annotations";
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

  const { data: downloadData } = useQuery({
    queryKey: ["document-download", id],
    queryFn: () =>
      apiClient<{ url: string }>({
        url: `/api/v1/documents/${id}/download`,
        method: "GET",
      }),
    enabled: !!doc,
  });

  const { data: annotationsData } = useAnnotations(id);
  const annotations = annotationsData?.items ?? [];

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
    <div className="space-y-4">
      <div className="flex items-center justify-between">
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
        {downloadData?.url && (
          <Button variant="outline" size="sm" asChild>
            <a href={downloadData.url} target="_blank" rel="noreferrer">
              <Download className="mr-2 h-3.5 w-3.5" />
              Download
            </a>
          </Button>
        )}
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          {downloadData?.url && doc.type === "pdf" ? (
            <PdfViewer
              url={downloadData.url}
              annotations={annotations}
              selectedAnnotationId={selectedAnnotationId}
              onAnnotationClick={handleAnnotationClick}
              onCreateHighlight={handleCreateHighlight}
            />
          ) : (
            <div className="flex items-center justify-center rounded-md border h-[400px] text-muted-foreground">
              Preview not available for {doc.type?.toUpperCase() ?? "this"} format
            </div>
          )}
        </div>
        <div>
          <Tabs defaultValue="metadata">
            <TabsList className="w-full">
              <TabsTrigger value="metadata" className="flex-1">Metadata</TabsTrigger>
              <TabsTrigger value="annotations" className="flex-1">
                Annotations ({annotations.length})
              </TabsTrigger>
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
          </Tabs>
        </div>
      </div>
    </div>
  );
}
