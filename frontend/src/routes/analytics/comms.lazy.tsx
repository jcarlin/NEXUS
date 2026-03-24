import { createLazyFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { apiClient } from "@/api/client";
import { useViewState } from "@/hooks/use-view-state";
import { CommMatrix, type MatrixEntry } from "@/components/analytics/comm-matrix";
import { CommDrilldown } from "@/components/analytics/comm-drilldown";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { PaginatedResponse } from "@/types";
import type { ThreadResponse } from "@/api/generated/schemas";

interface CommMatrixApiResponse {
  pairs: Array<{
    sender_name: string;
    sender_email: string;
    recipient_name: string;
    recipient_email: string;
    relationship_type: string;
    message_count: number;
    earliest: string;
    latest: string;
  }>;
  matter_id?: string;
}

export const Route = createLazyFileRoute("/analytics/comms")({
  component: CommsMatrixPage,
});

function CommsMatrixPage() {
  const [vs, setVS] = useViewState("/analytics/comms", { activeTab: "matrix" });
  const [drilldown, setDrilldown] = useState<{ personA: string; personB: string } | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["communication-matrix"],
    queryFn: () =>
      apiClient<CommMatrixApiResponse>({
        url: "/api/v1/analytics/communication-matrix",
        method: "GET",
      }),
  });

  const matrix: MatrixEntry[] = (data?.pairs ?? []).map((p) => ({
    sender: p.sender_name,
    receiver: p.recipient_name,
    count: p.message_count,
  }));
  const entities = [...new Set((data?.pairs ?? []).flatMap((p) => [p.sender_name, p.recipient_name]))];

  return (
    <div className="space-y-6 animate-page-in">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Communication Analysis</h1>
        <p className="text-sm text-muted-foreground">
          Visualize communication patterns between entities and explore email threads.
        </p>
      </div>

      <Tabs value={vs.activeTab} onValueChange={(v) => setVS({ activeTab: v })}>
        <TabsList>
          <TabsTrigger value="matrix">Matrix</TabsTrigger>
          <TabsTrigger value="threads">Email Threads</TabsTrigger>
        </TabsList>

        <TabsContent value="matrix">
          <CommMatrix
            matrix={matrix}
            entities={entities}
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
        </TabsContent>

        <TabsContent value="threads">
          <EmailThreadsPanel />
        </TabsContent>
      </Tabs>
    </div>
  );
}

function EmailThreadsPanel() {
  const { data, isLoading } = useQuery({
    queryKey: ["edrm-threads"],
    queryFn: () =>
      apiClient<PaginatedResponse<ThreadResponse>>({
        url: "/api/v1/edrm/threads",
        method: "GET",
        params: { limit: 100 },
      }),
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Email Threads</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading && <p className="text-sm text-muted-foreground">Loading threads...</p>}
        {data && data.items.length === 0 && (
          <p className="text-sm text-muted-foreground">No email threads found.</p>
        )}
        {data && data.items.length > 0 && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Thread ID</TableHead>
                <TableHead>Subject</TableHead>
                <TableHead className="text-right">Messages</TableHead>
                <TableHead>Earliest</TableHead>
                <TableHead>Latest</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.items.map((thread) => (
                <TableRow key={thread.thread_id}>
                  <TableCell className="font-mono text-xs">{thread.thread_id}</TableCell>
                  <TableCell>{thread.subject ?? "--"}</TableCell>
                  <TableCell className="text-right tabular-nums">{thread.message_count}</TableCell>
                  <TableCell className="text-muted-foreground whitespace-nowrap">
                    {thread.earliest ? new Date(thread.earliest).toLocaleDateString() : "--"}
                  </TableCell>
                  <TableCell className="text-muted-foreground whitespace-nowrap">
                    {thread.latest ? new Date(thread.latest).toLocaleDateString() : "--"}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
