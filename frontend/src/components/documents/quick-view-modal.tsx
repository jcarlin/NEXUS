import { Link } from "@tanstack/react-router";
import { ExternalLink } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { DocumentViewer } from "./document-viewer";

interface QuickViewModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  documentId: string;
  filename: string;
  page?: number | null;
  excerpt?: string;
  score?: number;
  downloadUrl?: string;
  documentType?: string | null;
}

export function QuickViewModal({
  open,
  onOpenChange,
  documentId,
  filename,
  page,
  excerpt,
  score,
  downloadUrl,
  documentType,
}: QuickViewModalProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[85vh] flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <span className="truncate">{filename}</span>
            {page && <Badge variant="outline">p. {page}</Badge>}
            {score != null && (
              <Badge variant="secondary">{(score * 100).toFixed(0)}% match</Badge>
            )}
          </DialogTitle>
        </DialogHeader>

        <div className="flex-1 min-h-0 overflow-auto">
          {downloadUrl ? (
            <DocumentViewer
              url={downloadUrl}
              filename={filename}
              type={documentType}
              compact
            />
          ) : excerpt ? (
            <div className="rounded-md bg-muted p-4 text-sm leading-relaxed">
              {excerpt}
            </div>
          ) : null}
        </div>

        <div className="flex justify-end pt-2 border-t">
          <Button variant="outline" size="sm" asChild>
            <Link
              to="/documents/$id"
              params={{ id: documentId }}
              search={page ? { page } : undefined}
            >
              <ExternalLink className="mr-2 h-3.5 w-3.5" />
              Full View
            </Link>
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
