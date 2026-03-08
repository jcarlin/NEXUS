import { useState } from "react";
import { ZoomIn, ZoomOut, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";

interface ImageViewerProps {
  url: string;
  filename: string;
  compact?: boolean;
}

export function ImageViewer({ url, filename, compact }: ImageViewerProps) {
  const [scale, setScale] = useState(1.0);
  const [error, setError] = useState(false);

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 rounded-md border p-8 text-muted-foreground">
        <AlertCircle className="h-8 w-8" />
        <p className="text-sm">Failed to load image</p>
      </div>
    );
  }

  const maxH = compact ? "max-h-[60vh]" : "";

  return (
    <div className="flex h-full flex-col items-center gap-3">
      <div className="flex shrink-0 items-center gap-1">
        <Button
          variant="outline"
          size="icon"
          onClick={() => setScale((s) => Math.max(0.25, s - 0.25))}
        >
          <ZoomOut className="h-4 w-4" />
        </Button>
        <span className="w-12 text-center text-xs text-muted-foreground">
          {Math.round(scale * 100)}%
        </span>
        <Button
          variant="outline"
          size="icon"
          onClick={() => setScale((s) => Math.min(5, s + 0.25))}
        >
          <ZoomIn className="h-4 w-4" />
        </Button>
      </div>

      <div className={`overflow-auto rounded border bg-muted/30 ${maxH} ${!compact ? "min-h-0 w-full flex-1" : ""}`}>
        <img
          src={url}
          alt={filename}
          style={{ transform: `scale(${scale})`, transformOrigin: "top left" }}
          className="max-w-none"
          onError={() => setError(true)}
        />
      </div>
    </div>
  );
}
