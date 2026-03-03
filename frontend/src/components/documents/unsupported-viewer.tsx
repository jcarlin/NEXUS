import { FileQuestion, Download } from "lucide-react";
import { Button } from "@/components/ui/button";

interface UnsupportedViewerProps {
  filename: string;
  downloadUrl?: string;
  type?: string | null;
}

export function UnsupportedViewer({ filename, downloadUrl, type }: UnsupportedViewerProps) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-md border p-12 text-muted-foreground">
      <FileQuestion className="h-12 w-12" />
      <p className="text-sm">
        Preview not available for {type?.toUpperCase() ?? "this"} format
      </p>
      <p className="text-xs">{filename}</p>
      {downloadUrl && (
        <Button variant="outline" size="sm" asChild>
          <a href={downloadUrl} target="_blank" rel="noreferrer">
            <Download className="mr-2 h-3.5 w-3.5" />
            Download
          </a>
        </Button>
      )}
    </div>
  );
}
