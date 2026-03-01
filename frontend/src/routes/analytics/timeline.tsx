import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { apiClient } from "@/api/client";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { TimelineView } from "@/components/analytics/timeline-view";
import type { TimelineEvent } from "@/types";

export const Route = createFileRoute("/analytics/timeline")({
  component: TimelinePage,
});

function TimelinePage() {
  const [entity, setEntity] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");

  const trimmedEntity = entity.trim();

  const { data, isLoading } = useQuery({
    queryKey: ["timeline", trimmedEntity, startDate, endDate],
    queryFn: () =>
      apiClient<TimelineEvent[]>({
        url: `/api/v1/graph/timeline/${encodeURIComponent(trimmedEntity)}`,
        method: "GET",
        params: {
          start_date: startDate || undefined,
          end_date: endDate || undefined,
        },
      }),
    enabled: !!trimmedEntity,
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Timeline</h1>
        <p className="text-sm text-muted-foreground">
          Chronological view of events for an entity.
        </p>
      </div>

      <div className="flex flex-wrap items-end gap-4">
        <div className="space-y-1.5">
          <Label htmlFor="entity-name">Entity name</Label>
          <Input
            id="entity-name"
            placeholder="e.g. John Smith"
            value={entity}
            onChange={(e) => setEntity(e.target.value)}
            className="w-[240px]"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="start-date">Start date</Label>
          <Input
            id="start-date"
            type="date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            className="w-[170px]"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="end-date">End date</Label>
          <Input
            id="end-date"
            type="date"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
            className="w-[170px]"
          />
        </div>
      </div>

      {!trimmedEntity ? (
        <p className="text-sm text-muted-foreground py-8 text-center">
          Enter an entity name above to view their timeline of events.
        </p>
      ) : (
        <TimelineView events={data ?? []} loading={isLoading} />
      )}
    </div>
  );
}
