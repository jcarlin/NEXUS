import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { apiClient } from "@/api/client";
import { CommMatrix, type MatrixEntry } from "@/components/analytics/comm-matrix";
import { CommDrilldown } from "@/components/analytics/comm-drilldown";

interface CommMatrixResponse {
  matrix: MatrixEntry[];
  entities: string[];
}

export const Route = createFileRoute("/analytics/comms")({
  component: CommsMatrixPage,
});

function CommsMatrixPage() {
  const [drilldown, setDrilldown] = useState<{ personA: string; personB: string } | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["communication-matrix"],
    queryFn: () =>
      apiClient<CommMatrixResponse>({
        url: "/api/v1/analytics/communication-matrix",
        method: "GET",
      }),
  });

  return (
    <div className="space-y-6 animate-page-in">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Communication Matrix</h1>
        <p className="text-sm text-muted-foreground">
          Visualize communication patterns between entities. Click a cell to see messages.
        </p>
      </div>

      <CommMatrix
        matrix={data?.matrix ?? []}
        entities={data?.entities ?? []}
        loading={isLoading}
        onCellClick={(sender, receiver) => setDrilldown({ personA: sender, personB: receiver })}
      />

      {drilldown && (
        <CommDrilldown
          personA={drilldown.personA}
          personB={drilldown.personB}
          open={!!drilldown}
          onOpenChange={(open) => { if (!open) setDrilldown(null); }}
        />
      )}
    </div>
  );
}
