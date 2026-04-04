import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDate } from "@/lib/utils";
import type { TimelineEvent } from "@/types";

interface TimelineResponse {
  entity: string;
  events: TimelineEvent[];
}

interface EntityTimelineProps {
  entityId: string;
  filterEntity?: string | null;
  centralEntity?: string;
}

export function EntityTimeline({ entityId, filterEntity, centralEntity }: EntityTimelineProps) {
  const { data, isLoading } = useQuery({
    queryKey: ["entity-timeline", entityId],
    queryFn: () =>
      apiClient<TimelineResponse>({
        url: `/api/v1/graph/timeline/${encodeURIComponent(entityId)}`,
        method: "GET",
      }),
  });

  // Filter events to those mentioning the selected connection entity
  const filteredEvents = useMemo(() => {
    if (!data?.events) return [];
    if (!filterEntity || filterEntity === centralEntity) return data.events;
    return data.events.filter((e) =>
      e.entities?.some((name) => name.toLowerCase() === filterEntity.toLowerCase()),
    );
  }, [data?.events, filterEntity, centralEntity]);

  const isFiltered = !!filterEntity && filterEntity !== centralEntity;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-sm font-medium">
          Timeline
          {isFiltered && (
            <Badge variant="secondary" className="text-[10px] font-normal">
              {filterEntity}
            </Badge>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="flex gap-4">
                <Skeleton className="h-4 w-20 shrink-0" />
                <Skeleton className="h-12 w-full" />
              </div>
            ))}
          </div>
        ) : !filteredEvents.length ? (
          <p className="text-sm text-muted-foreground">
            No timeline events found.
          </p>
        ) : (
          <div className="relative space-y-0">
            {/* Vertical line */}
            <div className="absolute left-[83px] top-0 bottom-0 w-px bg-border" />

            {filteredEvents.map((event, i) => (
              <div key={i} className="flex gap-4 py-3 relative">
                <div className="w-[72px] shrink-0 text-right">
                  {event.date ? (
                    <span className="text-xs font-medium text-muted-foreground">
                      {formatDate(event.date)}
                    </span>
                  ) : (
                    <span className="text-xs text-muted-foreground">
                      Unknown
                    </span>
                  )}
                </div>
                {/* Dot on the line */}
                <div className="relative flex items-start">
                  <div className="absolute -left-[5px] top-1 h-2.5 w-2.5 rounded-full bg-primary border-2 border-background" />
                </div>
                <div className="pl-4 min-w-0">
                  <p className="text-sm">{event.description}</p>
                  {event.entities?.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-1">
                      {event.entities.map((e) => (
                        <Badge
                          key={e}
                          variant="secondary"
                          className="text-[10px]"
                        >
                          {e}
                        </Badge>
                      ))}
                    </div>
                  )}
                  {event.document_source && (
                    <p className="text-xs text-muted-foreground mt-1">
                      Source: {event.document_source}
                    </p>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
