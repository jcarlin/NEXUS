import { createLazyFileRoute } from "@tanstack/react-router";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Switch } from "@/components/ui/switch";
import { PipelineSummary } from "@/components/admin/pipeline/pipeline-summary";
import { JobTable } from "@/components/admin/pipeline/job-table";
import { BulkImportTable } from "@/components/admin/pipeline/bulk-import-table";
import { QueueControls } from "@/components/admin/pipeline/queue-controls";
import { LiveRefreshProvider, useLiveRefresh } from "@/hooks/use-live-refresh";

export const Route = createLazyFileRoute("/admin/pipeline")({
  component: PipelineMonitorPage,
});

function LiveToggle() {
  const { isLive, toggleLive } = useLiveRefresh();
  return (
    <div className="flex items-center gap-2">
      <span
        className={`h-2 w-2 rounded-full ${isLive ? "bg-green-500 animate-pulse" : "bg-muted-foreground"}`}
      />
      <span className="text-xs font-medium text-muted-foreground">
        {isLive ? "Live" : "Paused"}
      </span>
      <Switch size="sm" checked={isLive} onCheckedChange={toggleLive} />
    </div>
  );
}

function PipelineMonitorPage() {
  return (
    <LiveRefreshProvider>
      <div className="space-y-6 animate-page-in">
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Pipeline Monitor</h1>
            <p className="text-sm text-muted-foreground">
              Real-time view of all ingestion jobs, imports, and workers.
            </p>
          </div>
          <LiveToggle />
        </div>

        <PipelineSummary />

        <Tabs defaultValue="jobs">
          <TabsList>
            <TabsTrigger value="jobs">Jobs</TabsTrigger>
            <TabsTrigger value="imports">Bulk Imports</TabsTrigger>
            <TabsTrigger value="workers">Workers & Queues</TabsTrigger>
          </TabsList>
          <TabsContent value="jobs" className="mt-4">
            <JobTable />
          </TabsContent>
          <TabsContent value="imports" className="mt-4">
            <BulkImportTable />
          </TabsContent>
          <TabsContent value="workers" className="mt-4">
            <QueueControls />
          </TabsContent>
        </Tabs>
      </div>
    </LiveRefreshProvider>
  );
}
