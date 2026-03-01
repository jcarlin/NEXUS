import { Link } from "@tanstack/react-router";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDate } from "@/lib/utils";
import type { TimelineEvent } from "@/types";

interface TimelineViewProps {
  events: TimelineEvent[];
  loading?: boolean;
}

export function TimelineView({ events, loading }: TimelineViewProps) {
  if (loading) {
    return (
      <div className="space-y-4">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-20 w-full" />
        ))}
      </div>
    );
  }

  if (events.length === 0) {
    return (
      <p className="text-sm text-muted-foreground py-8 text-center">
        No events found for the selected filters.
      </p>
    );
  }

  return (
    <div className="relative ml-4 border-l border-border pl-6 space-y-6">
      {events.map((event, i) => (
        <div key={i} className="relative">
          {/* Dot on the timeline */}
          <div className="absolute -left-[31px] top-1 h-3 w-3 rounded-full border-2 border-primary bg-background" />

          <div className="rounded-md border p-4 space-y-2">
            {event.date && (
              <p className="text-xs font-medium text-muted-foreground">
                {formatDate(event.date)}
              </p>
            )}

            <p className="text-sm">{event.description}</p>

            {event.entities.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {event.entities.map((entity) => (
                  <Badge key={entity} variant="secondary" className="text-[10px]">
                    {entity}
                  </Badge>
                ))}
              </div>
            )}

            {event.document_source && (
              <Link
                to="/documents/$id"
                params={{ id: event.document_source }}
                className="text-xs text-primary hover:underline"
              >
                View source document
              </Link>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
