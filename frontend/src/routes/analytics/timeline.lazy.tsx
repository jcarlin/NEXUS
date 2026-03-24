import { createLazyFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useState, useEffect } from "react";
import { apiClient } from "@/api/client";
import { useDebounce } from "@/hooks/use-debounce";
import { useViewState } from "@/hooks/use-view-state";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { TimelineView } from "@/components/analytics/timeline-view";
import type { TimelineEvent } from "@/types";

export const Route = createLazyFileRoute("/analytics/timeline")({
  component: TimelinePage,
});

function TimelinePage() {
  const [vs, setVS] = useViewState("/analytics/timeline", {
    entity: "",
    startDate: "",
    endDate: "",
  });
  const [entityInput, setEntityInput] = useState(vs.entity);
  const trimmedEntity = entityInput.trim();
  const debouncedEntity = useDebounce(trimmedEntity, 500);

  // Sync debounced entity back to persisted view state
  useEffect(() => {
    setVS({ entity: debouncedEntity });
  }, [debouncedEntity, setVS]);

  const { data, isLoading } = useQuery({
    queryKey: ["timeline", debouncedEntity, vs.startDate, vs.endDate],
    queryFn: () =>
      apiClient<TimelineEvent[]>({
        url: `/api/v1/graph/timeline/${encodeURIComponent(debouncedEntity)}`,
        method: "GET",
        params: {
          start_date: vs.startDate || undefined,
          end_date: vs.endDate || undefined,
        },
      }),
    enabled: !!debouncedEntity,
    retry: false,
  });

  const events = Array.isArray(data) ? data : [];

  return (
    <div className="space-y-6 animate-page-in">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Timeline</h1>
        <p className="text-sm text-muted-foreground">
          Chronological view of events for an entity.
        </p>
      </div>

      <div className="flex flex-wrap items-end gap-4">
        <div className="space-y-1.5">
          <Label htmlFor="entity-name">Entity name</Label>
          <Input
            id="entity-name"
            placeholder="e.g. Sarah Chen"
            value={entityInput}
            onChange={(e) => setEntityInput(e.target.value)}
            className="w-[240px]"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="start-date">Start date</Label>
          <Input
            id="start-date"
            type="date"
            value={vs.startDate}
            onChange={(e) => setVS({ startDate: e.target.value })}
            className="w-[170px]"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="end-date">End date</Label>
          <Input
            id="end-date"
            type="date"
            value={vs.endDate}
            onChange={(e) => setVS({ endDate: e.target.value })}
            className="w-[170px]"
          />
        </div>
      </div>

      {!trimmedEntity ? (
        <p className="text-sm text-muted-foreground py-8 text-center">
          Enter an entity name above to view their timeline of events.
        </p>
      ) : (
        <TimelineView events={events} loading={isLoading} />
      )}
    </div>
  );
}
