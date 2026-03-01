import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Link } from "@tanstack/react-router";
import type { SourceDocument } from "@/types";

interface CitationMarkerProps {
  index: number;
  source: SourceDocument;
}

export function CitationMarker({ index, source }: CitationMarkerProps) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Link
          to="/documents"
          search={{ id: source.id }}
          className="ml-0.5 inline-flex h-4 min-w-4 items-center justify-center rounded bg-primary/15 px-1 text-[10px] font-semibold text-primary hover:bg-primary/25"
        >
          {index + 1}
        </Link>
      </TooltipTrigger>
      <TooltipContent side="top" className="max-w-72">
        <p className="font-medium">{source.filename}</p>
        {source.page != null && (
          <p className="text-xs opacity-80">Page {source.page}</p>
        )}
        <p className="mt-1 line-clamp-3 text-xs opacity-70">
          {source.chunk_text}
        </p>
      </TooltipContent>
    </Tooltip>
  );
}
