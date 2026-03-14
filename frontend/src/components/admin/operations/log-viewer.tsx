import { useState, useEffect, useRef, useCallback } from "react";
import { Search, Pause, Play, Trash2, Download } from "lucide-react";
import { apiFetchRaw } from "@/api/client";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

const MAX_LINES = 5000;

interface LogViewerDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  containerName: string;
  serviceName: string;
}

export function LogViewerDialog({
  open,
  onOpenChange,
  containerName,
  serviceName,
}: LogViewerDialogProps) {
  const [lines, setLines] = useState<string[]>([]);
  const [paused, setPaused] = useState(false);
  const [connected, setConnected] = useState(false);
  const [search, setSearch] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const pausedRef = useRef(false);

  // Keep pausedRef in sync
  useEffect(() => {
    pausedRef.current = paused;
  }, [paused]);

  const scrollToBottom = useCallback(() => {
    if (pausedRef.current) return;
    const el = scrollRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, []);

  useEffect(() => {
    if (!open) {
      // Clean up on close
      abortRef.current?.abort();
      abortRef.current = null;
      setLines([]);
      setPaused(false);
      setConnected(false);
      setSearch("");
      return;
    }

    const controller = new AbortController();
    abortRef.current = controller;

    async function streamLogs() {
      try {
        const response = await apiFetchRaw(
          `/api/v1/admin/operations/containers/${containerName}/logs/stream`,
          controller.signal,
        );
        setConnected(true);

        const reader = response.body?.getReader();
        if (!reader) return;

        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const parts = buffer.split("\n");
          // Keep the last incomplete part in the buffer
          buffer = parts.pop() ?? "";

          if (parts.length > 0) {
            setLines((prev) => {
              const updated = [...prev, ...parts];
              if (updated.length > MAX_LINES) {
                return updated.slice(updated.length - MAX_LINES);
              }
              return updated;
            });
            // Schedule scroll after render
            requestAnimationFrame(scrollToBottom);
          }
        }
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") {
          // Expected on cleanup
          return;
        }
        // Stream ended or errored
      } finally {
        setConnected(false);
      }
    }

    streamLogs();

    return () => {
      controller.abort();
    };
  }, [open, containerName, scrollToBottom]);

  const filteredLines = search
    ? lines.filter((line) =>
        line.toLowerCase().includes(search.toLowerCase()),
      )
    : lines;

  function handleClear() {
    setLines([]);
  }

  function handleDownload() {
    const blob = new Blob([lines.join("\n")], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${containerName}-logs.txt`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl h-[80vh] flex flex-col">
        <DialogHeader>
          <div className="flex items-center gap-2">
            <DialogTitle className="text-base">
              Logs: {serviceName}
            </DialogTitle>
            <span
              className={cn(
                "h-2 w-2 rounded-full shrink-0",
                connected ? "bg-green-500" : "bg-gray-400",
              )}
            />
            {connected && (
              <span className="text-[10px] text-muted-foreground">Live</span>
            )}
          </div>
        </DialogHeader>

        {/* Controls */}
        <div className="flex items-center gap-2 shrink-0">
          <Button
            size="sm"
            variant="outline"
            className="h-7 text-xs"
            onClick={() => setPaused((p) => !p)}
          >
            {paused ? (
              <>
                <Play className="mr-1 h-3 w-3" />
                Resume
              </>
            ) : (
              <>
                <Pause className="mr-1 h-3 w-3" />
                Pause
              </>
            )}
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="h-7 text-xs"
            onClick={handleClear}
          >
            <Trash2 className="mr-1 h-3 w-3" />
            Clear
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="h-7 text-xs"
            onClick={handleDownload}
          >
            <Download className="mr-1 h-3 w-3" />
            Download
          </Button>
          <div className="relative flex-1 max-w-xs ml-auto">
            <Search className="absolute left-2 top-1/2 h-3 w-3 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Filter logs..."
              className="h-7 pl-7 text-xs"
            />
          </div>
        </div>

        {/* Log content */}
        <div
          ref={scrollRef}
          className="flex-1 min-h-0 overflow-auto rounded-md border bg-muted/30 p-3"
        >
          <pre className="font-mono text-xs leading-5 whitespace-pre-wrap break-all">
            {filteredLines.length === 0 ? (
              <span className="text-muted-foreground">
                {connected
                  ? "Waiting for log output..."
                  : "Connecting to log stream..."}
              </span>
            ) : (
              filteredLines.map((line, i) => (
                <div key={i} className="hover:bg-muted/50">
                  {line}
                </div>
              ))
            )}
          </pre>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between text-[10px] text-muted-foreground shrink-0">
          <span>
            {filteredLines.length.toLocaleString()} lines
            {search ? ` (filtered from ${lines.length.toLocaleString()})` : ""}
          </span>
          <span>Max buffer: {MAX_LINES.toLocaleString()} lines</span>
        </div>
      </DialogContent>
    </Dialog>
  );
}
