import { useState, useEffect } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { AlertCircle } from "lucide-react";

interface TextViewerProps {
  url: string;
  compact?: boolean;
}

export function TextViewer({ url, compact }: TextViewerProps) {
  const [content, setContent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setContent(null);
    setError(null);

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

  const maxH = compact ? "max-h-[60vh]" : "max-h-[calc(100vh-300px)]";

  return (
    <ScrollArea className={`rounded-md border bg-muted/30 ${maxH}`}>
      <pre className="whitespace-pre-wrap break-words p-4 text-sm leading-relaxed">
        {content}
      </pre>
    </ScrollArea>
  );
}
