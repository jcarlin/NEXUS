import { createLazyFileRoute } from "@tanstack/react-router";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { PipelineSummary } from "@/components/admin/pipeline/pipeline-summary";
import { JobTable } from "@/components/admin/pipeline/job-table";
import { BulkImportTable } from "@/components/admin/pipeline/bulk-import-table";
import { QueueControls } from "@/components/admin/pipeline/queue-controls";

export const Route = createLazyFileRoute("/admin/pipeline")({
  component: PipelineMonitorPage,
});

function PipelineMonitorPage() {
  return (
    <div className="space-y-6 animate-page-in">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Pipeline Monitor</h1>
        <p className="text-sm text-muted-foreground">
          Real-time view of all ingestion jobs, imports, and workers.
        </p>
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
  );
}
