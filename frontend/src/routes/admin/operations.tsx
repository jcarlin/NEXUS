import { createFileRoute } from "@tanstack/react-router";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ContainerGrid } from "@/components/admin/operations/container-grid";
import { CeleryPanel } from "@/components/admin/operations/celery-panel";
import { UptimeBar } from "@/components/admin/operations/uptime-bar";
import { DependencyDiagram } from "@/components/admin/operations/dependency-diagram";
import { PendingRestarts } from "@/components/admin/operations/pending-restarts";

export const Route = createFileRoute("/admin/operations")({
  component: OperationsPage,
});

function OperationsPage() {
  return (
    <div className="space-y-6 animate-page-in">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          Service Operations
        </h1>
        <p className="text-sm text-muted-foreground">
          Manage Docker containers, Celery workers, and monitor service health.
        </p>
      </div>
      <PendingRestarts />
      <UptimeBar />
      <Tabs defaultValue="infrastructure">
        <TabsList>
          <TabsTrigger value="infrastructure">Infrastructure</TabsTrigger>
          <TabsTrigger value="celery">Celery Workers</TabsTrigger>
          <TabsTrigger value="dependencies">Dependency Map</TabsTrigger>
        </TabsList>
        <TabsContent value="infrastructure" className="mt-4">
          <ContainerGrid />
        </TabsContent>
        <TabsContent value="celery" className="mt-4">
          <CeleryPanel />
        </TabsContent>
        <TabsContent value="dependencies" className="mt-4">
          <DependencyDiagram />
        </TabsContent>
      </Tabs>
    </div>
  );
}
